"""LLM-as-judge for explanations, and its agreement with the reviewer's ratings.

    python -m tally.judge sample   # 30 test explanations -> golden/explanations_to_rate.csv (for the reviewer)
    python -m tally.judge run      # queue/collect judge scores -> results/judge_scores.csv
    python -m tally.judge agree    # judge vs reviewer (golden/explanation_ratings.csv) -> results/judge.json

The judge sees the full resume; the screener only saw retrieved passages. So the judge can catch evidence the
screener missed, which is the failure mode that matters most here.
"""
from __future__ import annotations

import csv
import random
import sys

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

from . import golden, llm, screen
from .config import cfg, path, write_json
from .prompts import judge as judge_prompt

DIMS = ("grounded", "gaps_correct", "actionable")


def sample(n: int = 30):
    """Stratified by lane so shortlist and review explanations are both rated."""
    rng = random.Random(cfg()["seed"])
    rows = []
    for p in golden.pairs():
        if p["split"] != "test":
            continue
        try:
            r = screen.screen(p["job"], p["cand"])
        except llm.Pending:
            continue
        rows.append({"job": p["job"], "cand": p["cand"], "lane": r["lane"], "explanation": r["explanation"]})
    by = {ln: [r for r in rows if r["lane"] == ln] for ln in screen.LANES}
    quota = {"shortlist": min(8, len(by["shortlist"])), "low_priority": min(8, len(by["low_priority"]))}
    quota["review"] = n - sum(quota.values())
    pick = [r for ln, q in quota.items() for r in rng.sample(by[ln], min(q, len(by[ln])))]
    rng.shuffle(pick)
    with open(path("golden") / "explanations_to_rate.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job", "cand", "explanation"])
        w.writeheader()
        w.writerows({k: r[k] for k in ("job", "cand", "explanation")} for r in pick)
    print(f"{len(pick)} explanations -> golden/explanations_to_rate.csv")


def _items() -> list[dict]:
    with open(path("golden") / "explanations_to_rate.csv") as f:
        return list(csv.DictReader(f))


def run():
    out, pending = [], 0
    for it in _items():  # judge the exact text the reviewer rated, whichever provider is judging
        try:
            chk = screen.job_checklist(it["job"])
            s = llm.ask("judge", judge_prompt(screen.jobs()[it["job"]]["title"], chk["requirements"],
                                              screen.resumes()[it["cand"]]["text"], it["explanation"]))
        except llm.Pending:
            pending += 1
            continue
        out.append({"job": it["job"], "cand": it["cand"], **s.model_dump()})
    if pending:
        print(f"{pending} judge calls queued; answer the queue and re-run")
    with open(path("results") / "judge_scores.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job", "cand", *DIMS, "rationale"])
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} judged")


def agree():
    def load(p):
        with open(p) as f:
            return {(r["job"], r["cand"]): r for r in csv.DictReader(f)}
    judge = load(path("results") / "judge_scores.csv")
    human = load(path("golden") / "explanation_ratings.csv")
    keys = sorted(set(judge) & set(human))
    res = {"n": len(keys)}
    for d in DIMS:
        j = [int(judge[k][d]) for k in keys]
        h = [int(human[k][d]) for k in keys]
        res[d] = {"judge_mean": round(float(np.mean(j)), 2), "reviewer_mean": round(float(np.mean(h)), 2),
                  "weighted_kappa": round(float(cohen_kappa_score(h, j, weights="quadratic", labels=[1, 2, 3, 4, 5])), 3),
                  "exact": round(float(np.mean([a == b for a, b in zip(j, h)])), 3),
                  "within_1": round(float(np.mean([abs(a - b) <= 1 for a, b in zip(j, h)])), 3),
                  "spearman": round(float(spearmanr(j, h).statistic), 3) if len(set(j)) > 1 and len(set(h)) > 1 else None}
    flat = {f"{d} κw": res[d]["weighted_kappa"] for d in DIMS}
    flat.update({f"{d} within ±1": res[d]["within_1"] for d in DIMS})
    flat["pairs"] = len(keys)
    write_json(path("results") / "judge.json", {"agreement": flat, "detail": res})
    print(flat)


if __name__ == "__main__":
    {"sample": sample, "run": run, "agree": agree}[sys.argv[1]]()
