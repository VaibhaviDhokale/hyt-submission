"""Evaluation harness.

    python -m tally.evaluate tune         # shortlist threshold from dev jobs only -> results/thresholds.json
    python -m tally.evaluate metrics      # ranking + decision metrics on test (and dev) -> results/metrics.json
    python -m tally.evaluate baselines    # keyword overlap, TF-IDF vs the system -> results/baselines.json
    python -m tally.evaluate extraction   # checklist + profile extraction vs gold -> results/extraction.json
    python -m tally.evaluate all

Ground truth: golden/labels.csv (relevance 0-3, ideal shortlist|review). A "good" candidate is ideal=shortlist.
Cost = cost_missed_good x (good, not shortlisted) + cost_bad_shortlist x (shortlisted, not good).
"""
from __future__ import annotations

import math
import random
import re
import sys
from collections import defaultdict

import numpy as np
from rapidfuzz import fuzz
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer

from . import golden, llm, screen
from .config import cfg, path, read_json, write_json
from .retrieve import tokens


# ---------------------------------------------------------------- collect system outputs
def system_rows(split: str | None = None) -> list[dict]:
    """One row per labelled pair: label + system score/lane. Pairs still pending on the LLM are skipped (counted)."""
    labels = golden.labels()
    rows, missing = [], 0
    for p in golden.pairs():
        if split and p["split"] != split:
            continue
        lab = labels.get((p["job"], p["cand"]))
        if not lab:
            continue
        try:
            r = screen.screen(p["job"], p["cand"])
        except llm.Pending:
            missing += 1
            continue
        rows.append({"job": p["job"], "cand": p["cand"], "split": p["split"], "bucket": p["bucket"],
                     "rel": int(lab["relevance"]), "good": lab["ideal"] == "shortlist",
                     "score": r["score"], "lane": r["lane"], "reasons": r["reasons"],
                     "unmet_musts": sum(c["verdict"] != "met" for c in r["checklist"] if c["kind"] == "must")})
    if missing:
        print(f"warning: {missing} labelled pairs still pending on the LLM queue", file=sys.stderr)
    return rows


# ---------------------------------------------------------------- metric primitives
def ndcg(rels_in_rank_order: list[int], k: int) -> float:
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels_in_rank_order[:k]))
    ideal = sorted(rels_in_rank_order, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal[:k]))
    return dcg / idcg if idcg > 0 else float("nan")


def ranking(rows: list[dict], key: str = "score") -> dict:
    by_job = defaultdict(list)
    for r in rows:
        by_job[r["job"]].append(r)
    per = {}
    for j, rs in by_job.items():
        rs = sorted(rs, key=lambda r: -r[key])
        rels = [r["rel"] for r in rs]
        rho = spearmanr([r[key] for r in rs], rels).statistic if len(set(rels)) > 1 else float("nan")
        per[j] = {"ndcg@5": ndcg(rels, 5), "ndcg@10": ndcg(rels, 10), "p@5": np.mean([x >= 2 for x in rels[:5]]),
                  "spearman": rho}
    out = {m: float(np.nanmean([v[m] for v in per.values()])) for m in ("ndcg@5", "ndcg@10", "p@5", "spearman")}
    out["per_job"] = per
    return out


def decisions(rows: list[dict], shortlisted) -> dict:
    s = [r for r in rows if shortlisted(r)]
    good = [r for r in rows if r["good"]]
    tp = sum(r["good"] for r in s)
    c = cfg()["triage"]
    return {"shortlisted": len(s), "good": len(good), "true_shortlists": tp,
            "shortlist_precision": tp / len(s) if s else float("nan"),
            "shortlist_recall": tp / len(good) if good else float("nan"),
            "review_rate": 1 - len(s) / len(rows) if rows else float("nan"),
            "good_in_low_priority": sum(r["good"] and r.get("lane") == "low_priority" for r in rows),
            "cost": c["cost_missed_good"] * (len(good) - tp) + c["cost_bad_shortlist"] * (len(s) - tp)}


def bootstrap_ci(rows: list[dict], fn, n: int = 1000, seed: int = 0) -> list[float]:
    """Resample whole jobs (pairs within a job are not independent)."""
    jobs = sorted({r["job"] for r in rows})
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        pick = [rng.choice(jobs) for _ in jobs]
        rs = [dict(r, job=f"{r['job']}#{i}") for i, j in enumerate(pick) for r in rows if r["job"] == j]
        v = fn(rs)
        if not math.isnan(v):
            vals.append(v)
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)] if vals else [None, None]


# ---------------------------------------------------------------- threshold tuning (dev only)
def tune_threshold(rows: list[dict], key: str = "score", gate=None) -> dict:
    """Grid-search the shortlist line on dev; ties go to the highest (most conservative) value."""
    best = None
    for t in np.arange(0.30, 1.0001, 0.025):
        t = round(float(t), 3)
        d = decisions(rows, lambda r: r[key] >= t and (gate(r) if gate else True))
        if best is None or d["cost"] <= best[1]["cost"]:
            best = (t, d)
    return {"shortlist_at": best[0], "dev": best[1]}


def tune():
    rows = system_rows("dev")
    max_unmet = cfg()["triage"]["max_unmet_musts"]
    gate = lambda r: r["unmet_musts"] <= max_unmet and not (set(r["reasons"]) & screen.BLOCKING)
    res = tune_threshold(rows, gate=gate)
    # gate variants, compared on dev only (the policy above was picked from this table)
    variants = {}
    for name, m in [("all musts met", 0), ("<=1 must unmet (chosen)", 1), ("<=2 musts unmet", 2), ("score only", 99)]:
        g = lambda r, m=m: r["unmet_musts"] <= m and not (set(r["reasons"]) & screen.BLOCKING)
        v = tune_threshold(rows, gate=g)
        variants[name] = {"shortlist_at": v["shortlist_at"], **{k: v["dev"][k] for k in ("cost", "shortlist_precision", "shortlist_recall")}}
    out = {"shortlist_at": res["shortlist_at"], "low_priority_below": cfg()["triage"]["low_priority_below"],
           "tuned_on": "dev jobs " + ",".join(cfg()["golden"]["dev_jobs"]), "n_dev_pairs": len(rows), "dev": res["dev"], "gate_variants_dev": variants,
           "max_unmet_musts": max_unmet}
    write_json(path("results") / "thresholds.json", out)
    print(f"shortlist_at = {out['shortlist_at']} (dev cost {res['dev']['cost']}, {len(rows)} pairs)")


# ---------------------------------------------------------------- system metrics
def metrics():
    out = {}
    for split in ("dev", "test"):
        rows = system_rows(split)
        if not rows:
            continue
        rk = ranking(rows)
        dec = decisions(rows, lambda r: r["lane"] == "shortlist")
        out[split] = {"n_pairs": len(rows), "n_jobs": len({r["job"] for r in rows}),
                      **{k: round(v, 3) for k, v in rk.items() if k != "per_job"}, **dec,
                      "ndcg@5_ci": bootstrap_ci(rows, lambda rs: ranking(rs)["ndcg@5"]),
                      "lanes": {ln: sum(r["lane"] == ln for r in rows) for ln in screen.LANES},
                      "label_dist": {str(k): sum(r["rel"] == k for r in rows) for k in range(4)},
                      "per_job": {j: {k: round(float(v), 3) for k, v in m.items()} for j, m in rk["per_job"].items()}}
        if split == "test":
            out["test_pairs"] = [{k: r[k] for k in ("job", "cand", "bucket", "rel", "good", "score", "lane", "reasons")} for r in rows]
    out["thresholds"] = screen.thresholds()
    write_json(path("results") / "metrics.json", out)
    t = out.get("test", {})
    print(f"test: NDCG@5 {t.get('ndcg@5')} {t.get('ndcg@5_ci')}  P@5 {t.get('p@5')}  rho {t.get('spearman')}  "
          f"shortlist P/R {t.get('shortlist_precision')}/{t.get('shortlist_recall')}  review {t.get('review_rate')}  cost {t.get('cost')}")


# ---------------------------------------------------------------- baselines
def keyword_overlap(job_text: str, resume_text: str) -> float:
    a, b = set(tokens(job_text)), set(tokens(resume_text))
    return len(a & b) / len(a | b) if a | b else 0.0


def baseline_scores() -> dict[str, dict[tuple[str, str], float]]:
    jobs, res = screen.jobs(), screen.resumes()
    ps = golden.pairs()
    kw = {(p["job"], p["cand"]): keyword_overlap(jobs[p["job"]]["text"], res[p["cand"]]["text"]) for p in ps}
    vec = TfidfVectorizer(sublinear_tf=True, stop_words="english", min_df=1)
    docs = [jobs[j]["text"] for j in jobs] + [res[c]["text"] for c in sorted({p["cand"] for p in ps})]
    vec.fit(docs)
    tf = {}
    for p in ps:
        m = vec.transform([jobs[p["job"]]["text"], res[p["cand"]]["text"]])
        tf[(p["job"], p["cand"])] = float((m[0] @ m[1].T).toarray()[0, 0])
    return {"keyword overlap": kw, "TF-IDF cosine": tf}


def baselines():
    labels = golden.labels()
    sys_rows = {s: system_rows(s) for s in ("dev", "test")}
    systems = []
    for s in ("test",):
        rows = sys_rows[s]
        systems.append({"system": "Tally (checklist + rules)", **{k: round(v, 3) for k, v in ranking(rows).items() if k != "per_job"},
                        **decisions(rows, lambda r: r["lane"] == "shortlist")})
    for name, sc in baseline_scores().items():
        split_rows = {}
        for s in ("dev", "test"):
            split_rows[s] = [{"job": p["job"], "cand": p["cand"], "rel": int(labels[(p["job"], p["cand"])]["relevance"]),
                              "good": labels[(p["job"], p["cand"])]["ideal"] == "shortlist", "score": sc[(p["job"], p["cand"])]}
                             for p in golden.pairs() if p["split"] == s and (p["job"], p["cand"]) in labels]
            # rescale per job to [0,1] so one threshold fits every job
            by = defaultdict(list)
            for r in split_rows[s]:
                by[r["job"]].append(r["score"])
            for r in split_rows[s]:
                lo, hi = min(by[r["job"]]), max(by[r["job"]])
                r["score"] = (r["score"] - lo) / (hi - lo) if hi > lo else 0.0
        t = tune_threshold(split_rows["dev"])["shortlist_at"]
        rows = split_rows["test"]
        systems.append({"system": name, "threshold_from_dev": t,
                        **{k: round(v, 3) for k, v in ranking(rows).items() if k != "per_job"},
                        **decisions(rows, lambda r, t=t: r["score"] >= t),
                        "ndcg@5_ci": bootstrap_ci(rows, lambda rs: ranking(rs)["ndcg@5"])})
    systems[0]["ndcg@5_ci"] = bootstrap_ci(sys_rows["test"], lambda rs: ranking(rs)["ndcg@5"])
    write_json(path("results") / "baselines.json", {"split": "test", "systems": systems})
    for s in systems:
        print(f"{s['system']:<28} NDCG@5 {s['ndcg@5']:.3f}  P@5 {s['p@5']:.2f}  rho {s['spearman']:.2f}  "
              f"P {s['shortlist_precision']:.2f} R {s['shortlist_recall']:.2f}  cost {s['cost']}")


# ---------------------------------------------------------------- extraction vs gold
def _match(a: str, b: str) -> bool:
    return fuzz.token_set_ratio(a.lower(), b.lower()) >= 70


def _prf(pred: list[str], gold: list[str]) -> tuple[int, int, int]:
    tp_p = sum(any(_match(p, g) for g in gold) for p in pred)
    tp_g = sum(any(_match(p, g) for p in pred) for g in gold)
    return tp_p, len(pred), tp_g, len(gold)


def _f1(acc) -> dict:
    tpp, npred, tpg, ngold = (sum(x[i] for x in acc) for i in range(4))
    p = tpp / npred if npred else float("nan")
    r = tpg / ngold if ngold else float("nan")
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def extraction():
    g = path("golden")
    out = {}
    if (g / "jd_gold.json").exists():
        gold = read_json(g / "jd_gold.json")
        must, allr = [], []
        for j, v in gold.items():
            try:
                chk = screen.job_checklist(j)
            except llm.Pending:
                continue
            pm = [r["text"] + " " + r["jd_quote"] for r in chk["requirements"] if r["kind"] == "must"]
            pa = [r["text"] + " " + r["jd_quote"] for r in chk["requirements"]]
            must.append(_prf(pm, v["must"]))
            allr.append(_prf(pa, v["must"] + v.get("nice", [])))
        out["checklist_must"] = _f1(must)
        out["checklist_all"] = _f1(allr)
    if (g / "extraction_gold.json").exists():
        gold = read_json(g / "extraction_gold.json")
        certs, sw, edu, yerr = [], [], [], []
        for cid, v in gold.items():
            text = screen.resumes()[cid]["text"]
            try:
                prof = screen.resume_profile(text)
            except llm.Pending:
                continue
            certs.append(_prf(prof["certifications"], v.get("certifications", [])))
            sw.append(_prf(prof["software"], v.get("software", [])))
            best = max(prof["education"], key=lambda e: screen.EDU_RANK[e["level"]], default={"level": "none"})["level"]
            edu.append(best == v.get("education_level"))
            from .experience import years
            yerr.append(abs(years(prof["roles"], text)["relevant"] - float(v.get("finance_years") or 0)))
        out["certifications"] = _f1(certs)
        out["software"] = _f1(sw)
        out["education_accuracy"] = round(float(np.mean(edu)), 3) if edu else None
        out["finance_years_mae"] = round(float(np.mean(yerr)), 2) if yerr else None
        out["finance_years_within_1y"] = round(float(np.mean([e <= 1 for e in yerr])), 3) if yerr else None
        out["n_resumes"] = len(edu)
    write_json(path("results") / "extraction.json", out)
    print(out)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"tune": [tune], "metrics": [metrics], "baselines": [baselines], "extraction": [extraction],
             "all": [tune, metrics, baselines, extraction]}[cmd]
    for s in steps:
        s()


if __name__ == "__main__":
    main()
