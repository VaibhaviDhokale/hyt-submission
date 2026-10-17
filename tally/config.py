from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@lru_cache
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def path(key: str) -> Path:
    if key == "results" and os.getenv("TALLY_RESULTS"):  # e.g. results/gemini for a second provider's run
        p = ROOT / os.environ["TALLY_RESULTS"]
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = ROOT / cfg()["paths"][key]
    if p.suffix == "":
        p.mkdir(parents=True, exist_ok=True)
    return p


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def read_json(p: Path):
    return json.loads(Path(p).read_text())


def write_json(p: Path, obj) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def provider() -> str:
    return os.getenv("LLM_PROVIDER_TALLY") or cfg()["llm"]["provider"]
