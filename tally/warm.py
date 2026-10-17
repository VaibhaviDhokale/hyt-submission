"""Fill the cache for the current provider in parallel (live providers only).

    LLM_PROVIDER_TALLY=gemini python -m tally.warm --workers 6

Order matters: checklists and profiles first, because grading prompts are built from them. Then the fairness and
manipulation variants, then the judge. Failures are reported and left for a re-run (cached calls are free).
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import golden, robust, screen
from .clean import clean_resume
from .config import provider
from .judge import _items as judge_items


def _pool(fn, items, workers, label):
    t, ok, bad = time.time(), 0, []
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fn, *it): it for it in items}
        for f in as_completed(futs):
            try:
                f.result()
                ok += 1
            except Exception as e:  # keep going; report at the end
                bad.append((futs[f], str(e)[:160]))
    print(f"{label}: {ok} ok, {len(bad)} failed, {time.time() - t:.0f}s")
    for it, e in bad[:5]:
        print("   ", it, e)
    return bad


def variant_texts():
    """(job, text) for every fairness and manipulation variant, mirroring tally.robust."""
    out = []
    for job, cand in robust.fairness_bases():
        base = screen.resumes()[cand]["text"]
        for group, (tmpl, values) in robust.GROUPS.items():
            for v in values:
                edit = tmpl.format(v=v)
                out.append((job, edit + base if group == "name" else base + "\n" + edit))
    for job, cand in robust.adversarial_bases():
        base = screen.resumes()[cand]["text"]
        chk = screen.job_checklist(job)
        out.append((job, base))
        for name, payload in robust.ATTACKS.items():
            if name == "keyword_stuffing":
                payload = "\nSkills: " + ", ".join(r["text"] for r in chk["requirements"]) * 2
            out.append((job, base + payload))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if provider() == "queue":
        raise SystemExit("warm is for live providers; set LLM_PROVIDER_TALLY=gemini")
    w = a.workers
    pairs = golden.pairs()
    _pool(screen.job_checklist, [(j,) for j in screen.jobs()], w, "checklists")
    _pool(lambda c: screen.resume_profile(screen.resumes()[c]["text"]), [(c,) for c in {p["cand"] for p in pairs}], w, "profiles")
    _pool(screen.screen, [(p["job"], p["cand"]) for p in pairs], w, "grades")

    def run_variant(job, text):
        rec = clean_resume(text.replace("\n", "   "))
        screen.screen_text(job, rec["text"], rec)
    _pool(run_variant, variant_texts(), w, "fairness + manipulation variants")

    from .llm import ask
    from .prompts import judge as judge_prompt
    _pool(lambda it: ask("judge", judge_prompt(screen.jobs()[it["job"]]["title"],
                                               screen.job_checklist(it["job"])["requirements"],
                                               screen.resumes()[it["cand"]]["text"], it["explanation"])),
          [(it,) for it in judge_items()], w, "judge")


if __name__ == "__main__":
    main()
