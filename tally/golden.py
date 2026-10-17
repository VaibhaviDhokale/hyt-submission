"""Golden-set sampling and loading.

    python -m tally.golden sample      # -> golden/pairs.csv + golden/packets/J*.md (blind labelling packets)

Per job, 15 resumes: 5 BM25-top from the ACCOUNTANT/FINANCE pool, 5 random from that pool, 3 random from "near"
categories (banking, consulting, sales, business development) and 2 hard cases: the near/far resume that BM25
likes most (looks relevant, other field) and a core resume whose headline shares the job title's words but sits
outside BM25's top 30. BM25 here is independent of the system under test. Each resume is used for at most 2 jobs.
"""
from __future__ import annotations

import csv
import random
import sys

from rank_bm25 import BM25Okapi

from .config import cfg, path, read_json
from .retrieve import tokens

FIELDS = ["job", "cand", "split", "bucket"]


def sample() -> list[dict]:
    c = cfg()
    rng = random.Random(c["seed"])
    jobs = read_json(path("work") / "jobs.json")
    res = read_json(path("work") / "resumes.json")
    ids = sorted(res)
    bm25 = BM25Okapi([tokens(res[i]["text"]) for i in ids])
    uses: dict[str, int] = {}
    b = c["golden"]["buckets"]
    pairs = []

    def free(pool):
        return [i for i in pool if uses.get(i, 0) < 2]

    for jid, j in jobs.items():
        scores = dict(zip(ids, bm25.get_scores(tokens(j["title"] + " " + j["text"]))))
        core = [i for i in ids if res[i]["tier"] == "core"]
        other = [i for i in ids if res[i]["tier"] != "core"]
        by_bm25 = sorted(core, key=lambda i: -scores[i])
        chosen: list[tuple[str, str]] = []

        def take(pool, n, bucket):
            for i in pool:
                if n == 0:
                    break
                if i not in {x for x, _ in chosen} and uses.get(i, 0) < 2:
                    chosen.append((i, bucket))
                    n -= 1

        take(by_bm25, b["bm25_top"], "bm25_top")
        take(sorted(other, key=lambda i: -scores[i]), 1, "hard_lookalike")
        title_words = set(tokens(j["title"])) - {"sr", "senior", "manager", "specialist"}
        head = lambda i: set(tokens(res[i]["text"].splitlines()[0]))
        take([i for i in by_bm25[30:] if title_words & head(i)], b["hard"] - 1, "hard_title_match")
        take(rng.sample(free(core), len(free(core))), b["random_core"], "random_core")
        near = [i for i in other if res[i]["tier"] == "near"]
        take(rng.sample(free(near), len(free(near))), b["near"], "near")
        take(rng.sample(free(core), len(free(core))), c["golden"]["pairs_per_job"] - len(chosen), "random_core")
        rng.shuffle(chosen)  # labellers see no bucket order
        for i, bucket in chosen:
            uses[i] = uses.get(i, 0) + 1
            pairs.append({"job": jid, "cand": i, "split": j["split"], "bucket": bucket})
    return pairs


def write_packets(pairs: list[dict]) -> None:
    jobs = read_json(path("work") / "jobs.json")
    res = read_json(path("work") / "resumes.json")
    out = path("golden") / "packets"
    out.mkdir(exist_ok=True)
    for jid, j in jobs.items():
        lines = [f"# {jid}: {j['title']}", f"{j['company']} | {j['location']} | {j['level']} | {j['work_type']}", "",
                 "## Job posting", "", j["text"], ""]
        for p in [p for p in pairs if p["job"] == jid]:
            lines += [f"## Candidate {p['cand']}", "", "```", res[p["cand"]]["text"], "```", ""]
        (out / f"{jid}.md").write_text("\n".join(lines))


def pairs() -> list[dict]:
    with open(path("golden") / "pairs.csv") as f:
        return list(csv.DictReader(f))


def pairs_for(job_id: str) -> list[str]:
    return [p["cand"] for p in pairs() if p["job"] == job_id]


def labels() -> dict[tuple[str, str], dict]:
    f = path("golden") / "labels.csv"
    if not f.exists():
        return {}
    with open(f) as fh:
        return {(r["job"], r["cand"]): r for r in csv.DictReader(fh)}


def main():
    if sys.argv[1:] != ["sample"]:
        raise SystemExit("usage: python -m tally.golden sample")
    ps = sample()
    with open(path("golden") / "pairs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(ps)
    write_packets(ps)
    from collections import Counter
    print(len(ps), "pairs,", len({p['cand'] for p in ps}), "resumes", Counter(p["bucket"] for p in ps))


if __name__ == "__main__":
    main()
