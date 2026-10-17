"""Cross-model comparison: the same pipeline answered by Claude Sonnet (queue cache) and Gemini (live cache).

    python -m tally.compare        # needs both caches filled -> results/model_comparison.json

Both runs read only from the SQLite cache here (provider=queue for Sonnet; Gemini answers are looked up by key and
never re-requested), so this is free to re-run. Thresholds come from each model's own dev tuning.
"""
from __future__ import annotations

import os
from collections import Counter

import numpy as np
from scipy.stats import spearmanr

from . import golden, llm, screen
from .config import ROOT, cfg, read_json, write_json


class _CacheOnlyGemini:
    """Context: answer Gemini prompts from the cache only (a miss raises Pending instead of calling the API)."""

    def __enter__(self):
        self.prev = {k: os.environ.get(k) for k in ("LLM_PROVIDER_TALLY", "TALLY_RESULTS")}
        os.environ["LLM_PROVIDER_TALLY"] = "gemini"
        os.environ["TALLY_RESULTS"] = "results/gemini"
        self.orig = llm._gemini
        llm._gemini = lambda *a, **k: (_ for _ in ()).throw(llm.Pending("not cached"))
        return self

    def __exit__(self, *exc):
        llm._gemini = self.orig
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run_all() -> dict:
    out = {}
    for p in golden.pairs():
        try:
            out[(p["job"], p["cand"])] = screen.screen(p["job"], p["cand"])
        except llm.Pending:
            pass
    return out


def main():
    os.environ.pop("LLM_PROVIDER_TALLY", None)
    sonnet = _run_all()
    with _CacheOnlyGemini():
        gemini = _run_all()
        gem_chk = {j: screen.job_checklist(j) for j in screen.jobs()}
    son_chk = {j: screen.job_checklist(j) for j in screen.jobs()}
    keys = sorted(set(sonnet) & set(gemini))
    s = np.array([sonnet[k]["score"] for k in keys])
    g = np.array([gemini[k]["score"] for k in keys])
    lanes = Counter((sonnet[k]["lane"], gemini[k]["lane"]) for k in keys)

    # checklist size and must-have counts per job; verdict agreement only where the requirement text matches
    chk = {j: {"sonnet_reqs": len(son_chk[j]["requirements"]), "gemini_reqs": len(gem_chk[j]["requirements"]),
               "sonnet_musts": sum(r["kind"] == "must" for r in son_chk[j]["requirements"]),
               "gemini_musts": sum(r["kind"] == "must" for r in gem_chk[j]["requirements"])} for j in screen.jobs()}

    res = {
        "pairs_compared": len(keys),
        "score_spearman": round(float(spearmanr(s, g).statistic), 3),
        "score_mean_abs_diff": round(float(np.mean(np.abs(s - g))), 3),
        "same_lane": round(sum(v for (a, b), v in lanes.items() if a == b) / len(keys), 3),
        "lane_crosstab_sonnet_to_gemini": {f"{a} -> {b}": v for (a, b), v in sorted(lanes.items())},
        "shortlist_flips": sum(v for (a, b), v in lanes.items() if (a == "shortlist") != (b == "shortlist")),
        "checklists": chk,
        "thresholds": {"sonnet": read_json(ROOT / "results/thresholds.json"),
                       "gemini": read_json(ROOT / "results/gemini/thresholds.json")},
        "metrics": {"sonnet": read_json(ROOT / "results/metrics.json")["test"],
                    "gemini": read_json(ROOT / "results/gemini/metrics.json")["test"]},
        "model": {"sonnet": llm.AGENT_MODEL, "gemini": os.getenv("GEMINI_MODEL") or cfg()["llm"]["gemini_model"]},
    }
    for m in res["metrics"].values():
        m.pop("per_job", None)
    write_json(ROOT / "results/model_comparison.json", res)
    print({k: v for k, v in res.items() if k not in ("checklists", "thresholds", "metrics")})


if __name__ == "__main__":
    main()
