"""SQLite: LLM response cache, pending-prompt queue, recruiter actions. One file, committed for reproducibility."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

from .config import path

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm (
  key TEXT PRIMARY KEY, task TEXT, model TEXT, prompt_version TEXT, prompt TEXT, response TEXT, created REAL);
CREATE TABLE IF NOT EXISTS queue (
  key TEXT PRIMARY KEY, task TEXT, model TEXT, prompt_version TEXT, prompt TEXT, created REAL, batch TEXT);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, cand TEXT, action TEXT, note TEXT, at REAL);
"""


@contextmanager
def db():
    con = sqlite3.connect(path("db"), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def cache_get(key: str) -> str | None:
    with db() as c:
        r = c.execute("SELECT response FROM llm WHERE key=?", (key,)).fetchone()
    return r["response"] if r else None


def cache_put(key: str, task: str, model: str, pv: str, prompt: str, response: str) -> None:
    with db() as c:
        c.execute("INSERT OR REPLACE INTO llm VALUES (?,?,?,?,?,?,?)", (key, task, model, pv, prompt, response, time.time()))
        c.execute("DELETE FROM queue WHERE key=?", (key,))


def enqueue(key: str, task: str, model: str, pv: str, prompt: str) -> None:
    with db() as c:
        c.execute("INSERT OR IGNORE INTO queue (key,task,model,prompt_version,prompt,created) VALUES (?,?,?,?,?,?)",
                  (key, task, model, pv, prompt, time.time()))


def log_action(job: str, cand: str, action: str, note: str = "") -> None:
    with db() as c:
        c.execute("INSERT INTO actions (job,cand,action,note,at) VALUES (?,?,?,?,?)", (job, cand, action, note, time.time()))


def actions(job: str) -> dict[str, dict]:
    """Latest recruiter action per candidate for a job."""
    with db() as c:
        rows = c.execute("SELECT * FROM actions WHERE job=? ORDER BY id", (job,)).fetchall()
    return {r["cand"]: dict(r) for r in rows}
