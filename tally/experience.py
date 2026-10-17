"""Years of experience computed in code from the role dates the LLM copied out of the resume.

"present" resolves to the latest date written anywhere in that resume (the resume's own era): the Kaggle resumes
were written years before the 2024 postings, and resolving "present" to 2024 would hand everyone phantom years.
"""
from __future__ import annotations

import re

from .config import cfg

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def to_months(s: str | None) -> int | None:
    """'2014-03' -> months since year 0; '2014' -> mid-year. None if unparseable."""
    if not s:
        return None
    m = re.fullmatch(r"\s*(\d{4})(?:-(\d{1,2}))?\s*", s)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2) or 7)
    if not (1950 <= y <= 2030 and 1 <= mo <= 12):
        return None
    return y * 12 + (mo - 1)


def resume_present(text: str) -> int:
    """Latest month mentioned in the resume text (month-name or bare year), else the configured fallback."""
    best = None
    for mon, y in re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(19\d\d|20[0-2]\d)\b", text, re.I):
        v = int(y) * 12 + MONTHS[mon[:3].lower()] - 1
        best = v if best is None or v > best else best
    for y in re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", text):
        v = int(y) * 12 + 6
        best = v if best is None or v > best else best
    return best if best is not None else to_months(cfg()["present_fallback"])


def years(roles: list[dict], text: str) -> dict:
    """Total and finance-relevant years (overlaps merged, internships excluded), plus date quality."""
    present = resume_present(text)
    spans = {"all": [], "relevant": []}
    undated = 0
    for r in roles:
        s = to_months(r.get("start"))
        e = present if (r.get("end") or "").lower() == "present" else to_months(r.get("end"))
        if s is None or e is None or e < s:
            undated += 1
            continue
        e = min(e, present)
        if r.get("internship"):
            continue
        spans["all"].append((s, e))
        if r.get("finance_relevant"):
            spans["relevant"].append((s, e))
    out = {k: round(_union(v) / 12, 1) for k, v in spans.items()}
    out["undated_roles"] = undated
    out["dates_reliable"] = bool(roles) and undated <= len(roles) / 2
    return out


def _union(iv: list[tuple[int, int]]) -> int:
    total, cur = 0, None
    for s, e in sorted(iv):
        if cur and s <= cur[1]:
            cur = (cur[0], max(cur[1], e))
        else:
            if cur:
                total += cur[1] - cur[0]
            cur = (s, e)
    return total + (cur[1] - cur[0] if cur else 0)
