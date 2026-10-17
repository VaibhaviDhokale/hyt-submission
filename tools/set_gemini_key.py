"""Add or replace Gemini API keys in .env without the key ever being echoed, logged or put in shell history.

    .venv/bin/python tools/set_gemini_key.py

Each key is typed at a hidden prompt, checked with one tiny generateContent call (a key whose Google project is
blocked fails here, not halfway through a run), and only working keys are saved. One key -> GEMINI_API_KEY;
several -> also GEMINI_API_KEYS (comma-separated, rotated by tally.llm). .env is rewritten atomically, mode 600.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def read_env() -> list[str]:
    return ENV.read_text().splitlines() if ENV.exists() else []


def model() -> str:
    for line in read_env():
        if line.startswith("GEMINI_MODEL="):
            return line.split("=", 1)[1].strip() or "gemini-3.1-flash-lite"
    return "gemini-3.1-flash-lite"


BUSY = {429, 500, 503, 504}  # Google-side load or rate limits: says nothing about the key


def _call(url: str, key: str, body: bytes | None = None) -> tuple[int, str, str]:
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=60)
        return 200, "", ""
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        return e.code, err.get("status", ""), (err.get("message") or "")[:100]
    except Exception as e:  # network
        return 0, "NETWORK", e.__class__.__name__


FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]


def check(key: str) -> tuple[bool, str]:
    """True if the key authenticates and its project can generate with *some* model. One busy model (Google-side
    load) does not fail the key; the configured model is tried first, then steadier ones. ~30 s at most."""
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    code, status, msg = _call(f"{base}?pageSize=1", key)  # auth only; unaffected by model load
    if code != 200:
        if code == 0:
            return False, f"could not reach Google ({msg}); check your connection"
        return False, f"key rejected: {code} {status}: {msg}"
    body = json.dumps({"contents": [{"parts": [{"text": "Reply with the word ok."}]}]}).encode()
    busy = []
    try:
        for m in [model()] + [f for f in FALLBACK_MODELS if f != model()]:
            for attempt in range(2):
                code, status, msg = _call(f"{base}/{m}:generateContent", key, body)
                if code == 200:
                    note = "" if m == model() else (f" (via {m}; your configured {model()} was busy: the pipeline "
                                                    "retries busy calls, or set GEMINI_MODEL to a steadier model)")
                    return True, "works" + note
                if code not in BUSY:
                    hint = (" (this Google project is blocked; create the key in a new AI Studio project)"
                            if code == 403 else "")
                    return False, f"{code} {status}: {msg}{hint}"
                if attempt == 0:
                    print(f"  {m} busy ({code}), one retry in 3s...")
                    time.sleep(3)
            busy.append(m)
    except KeyboardInterrupt:
        print()
        return True, "check interrupted; key authenticates, saved unverified for generation"
    return True, f"key authenticates; every model was busy ({', '.join(busy)}): saved anyway (Google-side load)"


def write_env(keys: list[str]) -> None:
    drop = ("GEMINI_API_KEY=", "GEMINI_API_KEYS=")
    lines = [ln for ln in read_env() if not ln.startswith(drop)]
    lines.insert(0, f"GEMINI_API_KEY={keys[0]}")
    if len(keys) > 1:
        lines.insert(1, f"GEMINI_API_KEYS={','.join(keys)}")
    fd, tmp = tempfile.mkstemp(dir=ENV.parent, prefix=".env.")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)


def main():
    print(f"Gemini key setup for {ENV}  (model checked: {model()})")
    print("Keys are read at a hidden prompt: nothing appears as you paste. Press Enter on an empty prompt (or Ctrl-C) to finish; working keys are then saved.\n")
    keys = []
    while True:
        try:
            k = getpass.getpass(f"Gemini API key #{len(keys) + 1} (hidden, Enter or Ctrl-C to finish): ").strip()
        except (KeyboardInterrupt, EOFError):  # finishing with Ctrl-C/Ctrl-D still saves the keys that worked
            print()
            k = ""
        if not k:
            break
        ok, msg = check(k)
        print(f"  key ending ...{k[-4:]}: {msg}")
        if ok:
            keys.append(k)
        else:
            print("  not saved.")
    if not keys:
        print("\nNo working key entered; .env left unchanged.")
        sys.exit(1)
    write_env(keys)
    print(f"\nSaved {len(keys)} working key(s) to .env (permissions 600). To use Gemini for a run:")
    print("  LLM_PROVIDER_TALLY=gemini TALLY_RESULTS=results/gemini .venv/bin/python -m tally.warm --workers 6")


if __name__ == "__main__":
    main()
