"""One entry point, `ask(task, prompt)`, two providers, one cache.

- queue  (default for now): a cache miss is written to the SQLite queue and raises Pending. Prompts are exported
         to JSONL, answered by Claude Sonnet agents, and imported back after schema validation.
- gemini (LLM_PROVIDER_TALLY=gemini): live google-genai call with the same prompt and JSON schema.

Cache key = sha256(model | task | prompt_version | prompt), so switching provider never mixes answers.

    python -m tally.llm status
    python -m tally.llm export --size 12           # -> data/queue/batch_NNN.jsonl
    python -m tally.llm import data/queue/batch_NNN.answers.jsonl
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time

from pydantic import BaseModel, ValidationError

from . import store
from .config import ROOT, cfg, provider, sha
from .schemas import SCHEMAS

AGENT_MODEL = "claude-sonnet-agent"
QUEUE_DIR = ROOT / "data" / "queue"


class Pending(Exception):
    """The prompt is queued for an agent; re-run once answers are imported."""


def model_name() -> str:
    return os.getenv("GEMINI_MODEL") or cfg()["llm"]["gemini_model"] if provider() == "gemini" else AGENT_MODEL


def key_for(task: str, prompt: str, model: str | None = None) -> str:
    return sha(f"{model or model_name()}|{task}|{cfg()['llm']['prompt_version']}|{prompt}")


def ask(task: str, prompt: str) -> BaseModel:
    schema = SCHEMAS[task]
    model = model_name()
    key = key_for(task, prompt, model)
    hit = store.cache_get(key)
    if hit is not None:
        return schema.model_validate_json(hit)
    if provider() == "gemini":
        if os.getenv("TALLY_OFFLINE"):  # reproduce from the committed cache only; never call the API
            raise Pending(key)
        out = _gemini(prompt, schema, model)
        store.cache_put(key, task, model, cfg()["llm"]["prompt_version"], prompt, out.model_dump_json())
        return out
    store.enqueue(key, task, model, cfg()["llm"]["prompt_version"], prompt)
    raise Pending(key)


_KEYS: list[str] = []
_turn = itertools.count()


def _gemini_key() -> str:
    """GEMINI_API_KEYS (comma-separated) rotates calls across several keys to spread quota; else GEMINI_API_KEY."""
    if not _KEYS:
        _KEYS.extend(k.strip() for k in (os.getenv("GEMINI_API_KEYS") or os.environ["GEMINI_API_KEY"]).split(",") if k.strip())
    return _KEYS[next(_turn) % len(_KEYS)]


def _gemini(prompt: str, schema: type[BaseModel], model: str) -> BaseModel:
    from google import genai
    from google.genai import types

    conf = types.GenerateContentConfig(temperature=cfg()["llm"]["temperature"],
                                       response_mime_type="application/json", response_schema=schema)
    last = None
    for attempt in range(5):
        try:
            client = genai.Client(api_key=_gemini_key())  # next key on every attempt, so a 429 moves on
            r = client.models.generate_content(model=model, contents=prompt, config=conf)
            return schema.model_validate_json(r.text)
        except ValidationError as e:  # malformed JSON: retry once more with the error appended
            last = e
            prompt = f"{prompt}\n\nYour previous answer failed validation: {str(e)[:400]}. Return valid JSON."
        except Exception as e:  # rate limits / transient; auth errors fail fast
            last = e
            if any(c in str(e) for c in ("PERMISSION_DENIED", "API_KEY_INVALID", "UNAUTHENTICATED")):
                break
            time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"gemini failed after retries: {last}")


# ---------------------------------------------------------------- agent queue I/O
def export(size: int) -> list[str]:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    with store.db() as c:
        rows = c.execute("SELECT * FROM queue WHERE batch IS NULL ORDER BY task, created").fetchall()
        n0 = len([f for f in QUEUE_DIR.glob("batch_*.jsonl") if ".answers" not in f.name])
        files = []
        for i in range(0, len(rows), size):
            name = f"batch_{n0 + len(files) + 1:03d}"
            f = QUEUE_DIR / f"{name}.jsonl"
            with f.open("w") as fh:
                for r in rows[i:i + size]:
                    fh.write(json.dumps({"key": r["key"], "task": r["task"], "prompt": r["prompt"],
                                         "schema": SCHEMAS[r["task"]].model_json_schema()}) + "\n")
                    c.execute("UPDATE queue SET batch=? WHERE key=?", (name, r["key"]))
            files.append(str(f.relative_to(ROOT)))
    return files


def import_answers(fp: str) -> tuple[int, list[str]]:
    with store.db() as c:
        queued = {r["key"]: dict(r) for r in c.execute("SELECT * FROM queue").fetchall()}
    ok, bad, bad_keys = 0, [], []
    for line in open(fp):
        if not line.strip():
            continue
        a = json.loads(line)
        q = queued.get(a.get("key"))
        if not q:
            continue
        try:
            resp = a["response"] if isinstance(a["response"], str) else json.dumps(a["response"])
            SCHEMAS[q["task"]].model_validate_json(resp)
        except (ValidationError, KeyError, TypeError, ValueError) as e:
            bad.append(f"{q['key'][:10]}: {str(e)[:160]}")
            bad_keys.append(q["key"])
            continue
        store.cache_put(q["key"], q["task"], q["model"], q["prompt_version"], q["prompt"], resp)
        ok += 1
    with store.db() as c:  # failures go back to the un-batched queue so the next export retries them
        c.executemany("UPDATE queue SET batch=NULL WHERE key=?", [(k,) for k in bad_keys])
    return ok, bad


def status() -> dict:
    with store.db() as c:
        cached = dict(c.execute("SELECT task, COUNT(*) FROM llm GROUP BY task").fetchall())
        pending = dict(c.execute("SELECT task, COUNT(*) FROM queue GROUP BY task").fetchall())
    return {"provider": provider(), "model": model_name(), "cached": cached, "pending": pending}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    e = sub.add_parser("export")
    e.add_argument("--size", type=int, default=12)
    sh = sub.add_parser("show")
    sh.add_argument("file")
    i = sub.add_parser("import")
    i.add_argument("files", nargs="+")
    a = ap.parse_args()
    if a.cmd == "status":
        print(json.dumps(status(), indent=2))
    elif a.cmd == "show":  # plain-text view of a batch for the agent answering it
        for n, line in enumerate(open(a.file), 1):
            it = json.loads(line)
            print(f"===== ITEM {n} | key={it['key']} | task={it['task']}")
            print(it["prompt"])
            print(f"----- JSON schema for task '{it['task']}':")
            print(json.dumps(it["schema"]))
            print()
    elif a.cmd == "export":
        print("\n".join(export(a.size)) or "queue empty")
    else:
        for f in a.files:
            ok, bad = import_answers(f)
            print(f"{f}: imported {ok}, rejected {len(bad)}")
            for b in bad:
                print("  ", b)


if __name__ == "__main__":
    main()
