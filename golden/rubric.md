# Labelling rubric (finance & accounting)

Label each (job, candidate) pair from the job posting and the resume text **only**. Never look at the system's
output (`results/`, `data/tally.sqlite`, the app) while labelling.

## Step 1, once per job: write the job's must-haves first
Before reading any candidate, list what a recruiter would actually screen on for this posting in
`golden/jd_gold.json`: `{"J01": {"must": ["..."], "nice": ["..."]}, ...}`. Use short phrases ("CPA license",
"3+ years accounting", "bachelor's in accounting/finance", "NetSuite or similar ERP"). Skip soft traits and duties
any applicant would claim. This is also the gold standard for the checklist-extraction metric.

## Step 2: label each pair

**relevance** (0-3)

| | meaning | typical case |
|---|---|---|
| 3 | strong fit: meets every must-have with clear evidence | staff accountant with 3 years of GL/close work, for a staff accountant job |
| 2 | plausible: in the right field and level, misses or only partly shows **one** must-have | right experience, but no CPA where a CPA is required |
| 1 | weak: finance-adjacent but misses several must-haves, or wrong level by a wide margin | bank teller for a controller role; AP clerk for a tax senior manager role |
| 0 | not a fit: different field | chef, sales rep, teacher |

**ideal** (`shortlist` or `review`): `shortlist` = you would phone-screen this person with no further checks.
Use it for relevance 3, and for relevance 2 only if the missing piece is something a phone call settles.
Everything else is `review` (a human looks later; nobody is rejected by the system).

**missing**: the must-haves (from step 1) that the resume does not show, separated by `;`. Empty if none.

**note**: one short line on anything unusual (overqualified, career changer, gap, odd formatting).

Rules of thumb
- Years count only finance/accounting/audit/tax/payroll/banking-operations roles. "Current" means the latest date in
  that resume, not today.
- A skill listed in a skills section, never used in a role, counts as partial at best.
- Resumes are anonymised ("Company Name", "City , State"): never penalise that.
- Name, gender cues, school prestige, age and location never change the label (location is a note only).

## Step 3: extraction gold (24 resumes)
For the first two candidates listed in each job packet, write `golden/extraction_gold.json`:
`{"C123": {"certifications": [...], "education_level": "bachelor", "software": [...], "finance_years": 4.5}, ...}`.
education_level is one of none, high_school, associate, bachelor, master, doctorate (the highest held).
