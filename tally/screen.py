"""Screen candidates against a job: checklist -> profile -> retrieve -> grade -> score -> lane -> explanation.

    python -m tally.screen J02                 # rank the job's golden candidates
    python -m tally.screen J02 --cand C123     # one candidate, full detail

LLM steps: checklist (per job), profile (per resume), grade (per pair). Everything after that is code.
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache

from rapidfuzz import fuzz

from . import llm
from .config import cfg, path, read_json
from .experience import years
from .prompts import checklist as checklist_prompt
from .prompts import grade as grade_prompt
from .prompts import profile as profile_prompt
from .retrieve import Index

EDU_RANK = {"none": 0, "high_school": 1, "associate": 2, "bachelor": 3, "master": 4, "doctorate": 5}
LANES = ("shortlist", "review", "low_priority")
REASONS = {
    "MUST_NOT_MET": "A must-have has no evidence in the resume (check it before the interview)",
    "MUST_PARTIAL": "A must-have is only partly shown",
    "BORDERLINE": "Score is just under the shortlist line",
    "UNVERIFIED_QUOTE": "The grader quoted text that is not in the resume; that item got no credit",
    "INJECTION": "Resume contains instructions aimed at an AI screener",
    "THIN_RESUME": "Resume is too short to judge",
    "DATES_UNCLEAR": "Most roles have no usable dates, so years can't be computed",
    "LOCATION": "Candidate location differs from an on-site job (information only)",
    "KEYWORD_STUFFING": "One line of the resume repeats most of the posting's requirements",
}
BLOCKING = {"INJECTION", "THIN_RESUME", "DATES_UNCLEAR", "UNVERIFIED_QUOTE", "KEYWORD_STUFFING"}


@lru_cache
def jobs() -> dict:
    return read_json(path("work") / "jobs.json")


@lru_cache
def resumes() -> dict:
    return read_json(path("work") / "resumes.json")


def thresholds() -> dict:
    t = dict(cfg()["triage"])  # shortlist_at / low_priority_below / max_unmet_musts
    f = path("results") / "thresholds.json"
    if f.exists():
        t.update({k: v for k, v in read_json(f).items() if k in ("shortlist_at", "low_priority_below")})
    return t


# ---------------------------------------------------------------- LLM steps (cached)
def job_checklist(job_id: str) -> dict:
    j = jobs()[job_id]
    c = llm.ask("checklist", checklist_prompt(j["text"], j["title"])).model_dump()
    for i, r in enumerate(c["requirements"], 1):
        r["id"] = f"R{i}"
    return c


def resume_profile(text: str) -> dict:
    return llm.ask("profile", profile_prompt(text)).model_dump()


# ---------------------------------------------------------------- grading
def grade_code(r: dict, prof: dict, yrs: dict) -> dict | None:
    """Years and degree are compared in code. Returns None when the LLM should grade the requirement."""
    if r["category"] == "experience" and r.get("min_years"):
        need, have = r["min_years"], yrs["relevant"]
        v = "met" if have >= need else "partial" if have >= 0.6 * need or yrs["all"] >= need else "not_met"
        return {"verdict": v, "quote": "", "source": "code",
                "note": f"{have:g} finance-relevant years ({yrs['all']:g} total) vs {need:g} asked"}
    if r["category"] == "education" and r.get("min_education"):
        need = EDU_RANK[r["min_education"]]
        best = max([EDU_RANK[e["level"]] for e in prof["education"]] or [0])
        top = max(prof["education"], key=lambda e: EDU_RANK[e["level"]], default=None)
        v = "met" if best >= need else "partial" if best == need - 1 else "not_met"
        what = f"{top['level']}{' in ' + top['field'] if top and top.get('field') else ''}" if top else "no degree listed"
        return {"verdict": v, "quote": "", "source": "code", "note": f"{what} vs {r['min_education']} asked"}
    return None


def stuffing_ratio(requirements: list[dict], text: str) -> float:
    """Largest share of the requirements found verbatim in a single resume line. Real resumes peak at 0.2 on the
    golden set; a pasted requirement list scores 1.0."""
    reqs = [r["text"].lower() for r in requirements]
    best = 0.0
    for line in text.splitlines():
        if len(line.split()) >= 6 and reqs:
            best = max(best, sum(fuzz.partial_ratio(q, line.lower()) >= 90 for q in reqs) / len(reqs))
    return best


def quote_ok(quote: str, text: str) -> bool:
    q = " ".join(quote.split()).lower()
    return len(q) >= 4 and fuzz.partial_ratio(q, " ".join(text.split()).lower()) >= 90


def grade_pair(chk: dict, text: str, prof: dict, yrs: dict) -> list[dict]:
    rows, to_llm = [], []
    for r in chk["requirements"]:
        g = grade_code(r, prof, yrs)
        rows.append({**{k: r[k] for k in ("id", "text", "kind", "category")}, **(g or {})})
        if g is None:
            to_llm.append(r)
    if to_llm:
        idx = Index(text)
        ps = {r["id"]: idx.top(f"{r['text']} {r['jd_quote']}") for r in to_llm}
        out = {v.req: v for v in llm.ask("grade", grade_prompt(to_llm, ps)).verdicts}
        for row in rows:
            if "verdict" in row:
                continue
            v = out.get(row["id"])
            if v is None:
                row.update(verdict="not_met", quote="", note="grader returned nothing", source="llm")
            elif v.verdict != "not_met" and not quote_ok(v.quote, text):
                row.update(verdict="unverified", quote=v.quote, note=v.note, source="llm")
            else:
                row.update(verdict=v.verdict, quote=v.quote if v.verdict != "not_met" else "", note=v.note, source="llm")
    return rows


# ---------------------------------------------------------------- score + lane
def score(rows: list[dict]) -> float:
    s = cfg()["score"]
    w = {"must": s["must_weight"], "nice": s["nice_weight"]}
    num = sum(w[r["kind"]] * s["credit"].get(r["verdict"], 0.0) for r in rows)
    den = sum(w[r["kind"]] for r in rows)
    return round(num / den, 3) if den else 0.0


def lane(sc: float, rows: list[dict], flags: list[str], t: dict) -> tuple[str, list[str]]:
    musts = [r for r in rows if r["kind"] == "must"]
    reasons = list(flags)
    if any(r["verdict"] in ("not_met", "unverified") for r in musts):
        reasons.append("MUST_NOT_MET")
    if any(r["verdict"] == "partial" for r in musts):
        reasons.append("MUST_PARTIAL")
    if t["shortlist_at"] - 0.05 <= sc < t["shortlist_at"]:
        reasons.append("BORDERLINE")
    unmet = sum(r["verdict"] != "met" for r in musts)
    if sc >= t["shortlist_at"] and unmet <= t.get("max_unmet_musts", 0) and not (set(reasons) & BLOCKING):
        return "shortlist", reasons
    if sc < t["low_priority_below"] and "MUST_NOT_MET" in reasons and not (set(reasons) & BLOCKING):
        return "low_priority", reasons
    return "review", reasons


def explain(rows: list[dict], ln: str, reasons: list[str], yrs: dict) -> str:
    musts = [r for r in rows if r["kind"] == "must"]
    met = [r for r in musts if r["verdict"] == "met"]
    head = {"shortlist": "Shortlisted", "review": "Needs a recruiter's look", "low_priority": "Low priority"}[ln]
    parts = [f"{head}: shows {len(met)} of {len(musts)} must-haves; {yrs['relevant']:g} years in finance roles."]
    ev = [r for r in rows if r["verdict"] in ("met", "partial") and (r["quote"] or r["source"] == "code")]
    if ev:
        parts.append("Evidence: " + "; ".join(
            f"{r['text']} ({r['verdict']}) - " + (f"\"{r['quote']}\"" if r["quote"] else r["note"]) for r in ev[:4]) + ".")
    gaps = [r for r in sorted(rows, key=lambda r: r["kind"] != "must") if r["verdict"] in ("not_met", "unverified", "partial")]
    if gaps:
        parts.append("Gaps: " + "; ".join(f"{r['text']} [{r['kind']}, {r['verdict'].replace('_', ' ')}]" for r in gaps[:5]) + ".")
        first = next((g for g in gaps if g["kind"] == "must"), gaps[0])
        parts.append(f"Ask about: {first['text']}.")
    other = [REASONS[x] for x in reasons if x not in ("MUST_NOT_MET", "MUST_PARTIAL")]
    if other:
        parts.append("Note: " + "; ".join(other) + ".")
    return " ".join(parts)


# ---------------------------------------------------------------- public API
def screen_text(job_id: str, text: str, meta: dict | None = None) -> dict:
    """Screen one resume text for one job. Raises llm.Pending if an LLM answer is not cached yet."""
    meta = meta or {}
    chk = job_checklist(job_id)
    prof = resume_profile(text)
    yrs = years(prof["roles"], text)
    flags = []
    if meta.get("injection"):
        flags.append("INJECTION")
    if len(text.split()) < 150:
        flags.append("THIN_RESUME")
    if not yrs["dates_reliable"]:
        flags.append("DATES_UNCLEAR")
    if stuffing_ratio(chk["requirements"], text) >= 0.5:
        flags.append("KEYWORD_STUFFING")
    rows = grade_pair(chk, text, prof, yrs)
    if any(r["verdict"] == "unverified" for r in rows):
        flags.append("UNVERIFIED_QUOTE")
    if chk.get("remote") is False and prof.get("location") and chk.get("location") \
            and prof["location"].split(",")[-1].strip().lower() not in chk["location"].lower():
        flags.append("LOCATION")
    sc = score(rows)
    ln, reasons = lane(sc, rows, flags, thresholds())
    return {"job": job_id, "score": sc, "lane": ln, "reasons": reasons, "checklist": rows, "years": yrs,
            "profile": prof, "explanation": explain(rows, ln, reasons, yrs)}


def screen(job_id: str, cand_id: str) -> dict:
    r = resumes()[cand_id]
    return {"cand": cand_id, **screen_text(job_id, r["text"], r)}


def rank(job_id: str, cand_ids: list[str]) -> tuple[list[dict], int]:
    """Screen many; returns (results sorted best first, number still pending on the LLM queue)."""
    out, pending = [], 0
    try:
        job_checklist(job_id)
    except llm.Pending:
        return [], len(cand_ids)
    for c in cand_ids:
        try:
            out.append(screen(job_id, c))
        except llm.Pending:
            pending += 1
    order = {k: i for i, k in enumerate(LANES)}
    out.sort(key=lambda r: (-r["score"], order[r["lane"]]))
    return out, pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--cand")
    a = ap.parse_args()
    if a.cand:
        print(json.dumps(screen(a.job, a.cand), indent=2))
        return
    from .golden import pairs_for
    res, pending = rank(a.job, pairs_for(a.job))
    print(f"{a.job} {jobs()[a.job]['title']}: {len(res)} screened, {pending} pending")
    for r in res:
        print(f"  {r['cand']:>10}  {r['score']:.2f}  {r['lane']:<12} {','.join(r['reasons'])}")


if __name__ == "__main__":
    main()
