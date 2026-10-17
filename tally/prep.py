"""Build the masked working subsample from the two Kaggle CSVs.

    python -m tally.prep

Jobs: one arshkon posting per role slot in config.yaml (title regex, optional level, 300-900 words, seeded pick).
Resumes: every ACCOUNTANT/FINANCE resume, 10 from each "near" category, a few random others. Cleaned, PII-masked,
de-duplicated. Writes data/work/{jobs,resumes,manifest}.json. Raw text never leaves data/raw/.
"""
from __future__ import annotations

import re

import pandas as pd

from .clean import mask_pii, normalize
from .clean import clean_resume
from .config import cfg, path, sha, write_json


def select_jobs() -> dict:
    c = cfg()
    df = pd.read_csv(path("postings_csv"), usecols=[
        "job_id", "title", "company_name", "description", "location", "formatted_experience_level",
        "formatted_work_type", "skills_desc", "remote_allowed", "listed_time"])
    df = df.dropna(subset=["title", "description"])
    df["words"] = df.description.str.split().str.len()
    df = df[(df.words >= 300) & (df.words <= 900)]
    title = df.title.str.lower()
    jobs, used = {}, set()
    for jid, slot in c["job_slots"].items():
        pool = df[title.str.contains(slot["pattern"], regex=True)]
        if slot.get("level"):
            pool = pool[pool.formatted_experience_level == slot["level"]]
        pool = pool[~pool.job_id.isin(used)].sort_values("job_id")
        r = pool.sample(1, random_state=c["seed"]).iloc[0]
        used.add(r.job_id)
        body, _ = normalize(str(r.description))
        body, _ = mask_pii(body)
        jobs[jid] = {
            "id": jid,
            "source_job_id": int(r.job_id),
            "title": str(r.title),
            "company": str(r.company_name) if pd.notna(r.company_name) else "",
            "location": str(r.location),
            "level": str(r.formatted_experience_level) if pd.notna(r.formatted_experience_level) else "",
            "work_type": str(r.formatted_work_type) if pd.notna(r.formatted_work_type) else "",
            "text": body,
            "split": "dev" if jid in c["golden"]["dev_jobs"] else "test",
        }
    return jobs


def select_resumes() -> tuple[dict, dict]:
    c = cfg()
    rc = c["resumes"]
    df = pd.read_csv(path("resumes_csv"), usecols=["ID", "Resume_str", "Category"])
    parts = [df[df.Category.isin(rc["core_categories"])]]
    for cat in rc["near_categories"]:
        parts.append(df[df.Category == cat].sample(10, random_state=c["seed"]))
    far = df[~df.Category.isin(rc["core_categories"] + rc["near_categories"])]
    parts.append(far.sample(rc["far_sample"], random_state=c["seed"]))
    pool = pd.concat(parts)

    out, seen, dropped = {}, {}, {"duplicate": [], "too_short": []}
    for r in pool.itertuples():
        cr = clean_resume(r.Resume_str)
        rid = f"C{int(r.ID)}"
        if cr["words"] < rc["min_words"]:
            dropped["too_short"].append(rid)
            continue
        h = sha(re.sub(r"\W+", " ", cr["text"].lower()))
        if h in seen:
            dropped["duplicate"].append({"id": rid, "of": seen[h]})
            continue
        seen[h] = rid
        tier = "core" if r.Category in rc["core_categories"] else "near" if r.Category in rc["near_categories"] else "far"
        out[rid] = {"id": rid, "kaggle_category": r.Category, "tier": tier, **cr}
    return out, dropped


def main():
    work = path("work")
    jobs = select_jobs()
    resumes, dropped = select_resumes()
    write_json(work / "jobs.json", jobs)
    write_json(work / "resumes.json", resumes)
    write_json(work / "manifest.json", {
        "jobs": {j: {"title": v["title"], "source_job_id": v["source_job_id"], "split": v["split"]} for j, v in jobs.items()},
        "n_resumes": len(resumes),
        "by_tier": pd.Series([r["tier"] for r in resumes.values()]).value_counts().to_dict(),
        "dropped": dropped,
        "injection_flagged": [r["id"] for r in resumes.values() if r["injection"]],
    })
    print(f"{len(jobs)} jobs, {len(resumes)} resumes -> {work}")
    for j in jobs.values():
        print(f"  {j['id']} [{j['split']}] {j['title']} | {j['company']} | {j['level']} | {len(j['text'].split())}w")


if __name__ == "__main__":
    main()
