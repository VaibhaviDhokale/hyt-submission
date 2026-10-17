"""Split a resume into short passages and pull the best few for each requirement with BM25.

The grader only sees these passages, so its quotes are bounded and verifiable, and text elsewhere in the resume
(including any injected instructions) never reaches it. Cost: evidence phrased with none of the requirement's
words can be missed (REPORT, failure modes).
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

STOP = set("a an and or the of to in for with on at by as is are be from your our you we will this that".split())
# Finance vocabulary that BM25 can't bridge on its own. Expands the query side only.
SYNONYMS = {
    "ap": "accounts payable invoices vendor", "ar": "accounts receivable collections billing invoicing",
    "gl": "general ledger journal entries", "close": "month-end closing close reconciliations",
    "reconciliations": "reconcile reconciled reconciling", "erp": "sap oracle netsuite dynamics peoplesoft quickbooks",
    "cpa": "certified public accountant", "gaap": "generally accepted accounting principles us gaap",
    "excel": "spreadsheets pivot vlookup", "fp&a": "budgeting forecasting financial planning analysis variance",
    "payroll": "adp paychex wages payroll", "audit": "auditing auditor internal controls sox",
    "tax": "taxation returns 1040 1120 1065 irs", "bachelor": "degree bs ba bba university college",
}


def tokens(s: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9&]+", s.lower()):
        if w in STOP or len(w) < 2:
            continue
        for suf in ("ations", "ation", "ing", "ies", "ed", "s"):  # crude stemming, enough for finance prose
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def passages(text: str, max_words: int = 45) -> list[str]:
    """Lines, with long lines cut at sentence boundaries and tiny lines merged forward."""
    out, buf = [], ""
    for line in text.splitlines():
        for sent in re.split(r"(?<=[.;])\s+", line.strip()):
            buf = f"{buf} {sent}".strip() if buf else sent
            if len(buf.split()) >= 8:
                words = buf.split()
                for i in range(0, len(words), max_words):
                    out.append(" ".join(words[i:i + max_words]))
                buf = ""
    if buf:
        out.append(buf)
    return out


class Index:
    def __init__(self, text: str):
        self.passages = list(dict.fromkeys(passages(text))) or [text]  # resumes often repeat sections
        self.bm25 = BM25Okapi([tokens(p) or ["_"] for p in self.passages])

    def top(self, query: str, k: int = 5) -> list[str]:
        q = query.lower()
        q += " " + " ".join(v for key, v in SYNONYMS.items() if re.search(rf"\b{re.escape(key)}\b", q))
        scores = self.bm25.get_scores(tokens(q))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self.passages[i] for i in order[:k] if scores[i] > 0]
