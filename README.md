# Tally: screening assistant for finance & accounting roles

Tally reads a job posting, turns it into a checklist of requirements, and checks each applicant against that
checklist with a quoted piece of evidence per line. It then sorts applicants into **Shortlist**, **Needs review** or
**Low priority**. It never rejects anyone: only a recruiter can pass on a candidate, and the app asks for a written
reason.

Results: [REPORT.md](REPORT.md). Design choices: [DECISIONS.md](DECISIONS.md).

## Run it (about 5 minutes, no API key)

```bash
make setup          # Python 3.11 venv + pinned deps (uv if present, else pip)
make test           # unit tests
make reproduce      # every Sonnet number in REPORT.md, offline from the committed cache
make reproduce-gemini compare   # the Gemini re-run (REPORT §11), also offline
make app            # http://localhost:5057
.venv/bin/python tools/set_gemini_key.py   # add Gemini key(s) to .env at a hidden prompt, checked before saving
```

Windows (PowerShell), from the repo root:

```powershell
py -3.11 -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q tests
.\.venv\Scripts\python -m tally.evaluate all; .\.venv\Scripts\python -m tally.robust fairness
.\.venv\Scripts\python -m tally.robust adversarial; .\.venv\Scripts\python -m tally.judge agree
.\.venv\Scripts\python -m web.app
```

`make reproduce` reads only `data/work/` (masked subsample) and `data/tally.sqlite` (every LLM answer, keyed by
model + prompt). It never calls an API. The raw Kaggle CSVs are not in the repo.

## The app

* **Jobs**: 12 real postings, each with a bar showing how its 15 applicants split across the three lanes.
* **Triage inbox**: one applicant at a time, best first. You see the score ring, reason codes, the checklist (✓ met,
  ◐ partial, ✗ not shown) with the quote behind each line, a plain-English summary, and the masked resume with the
  evidence highlighted. Keys: `A` advance, `H` hold, `P` pass (needs a reason), `J`/`K` next and previous.
* **Posting & checklist**: the requirements read from the posting, each with the posting phrase it came from.
* **Add resume**: paste text and it is masked and screened. Uploads are held in memory only.
* **Evaluation**: the headline metrics, baselines, fairness, judge agreement and manipulation tests.

## How it works

```
posting ─► LLM: checklist (must / nice, category, years, degree, source quote)
resume  ─► clean (unicode, invisible chars, PII mask, injection regex) ─► LLM: profile (roles+dates, degrees, certs)
for each requirement:
   years / degree ─► computed in code from the profile
   everything else ─► BM25 picks 5 resume passages ─► LLM grades met / partial / not met + verbatim quote
                                                    ─► code checks the quote is really in the resume
score = Σ weight·credit / Σ weight     (must ×2, nice ×1; met 1, partial .5, not met 0)
lane  = shortlist if score ≥ 0.525, ≤ 1 must-have not fully met, no blocking flag; low priority if
        score < 0.35 with a must-have missing; otherwise needs review (reason codes say why)
```

The LLM never produces the score or the lane. It answers three narrow questions, and code does the rest.

## LLM providers

All LLM calls go through `tally/llm.py: ask(task, prompt)`, which returns schema-validated JSON and caches it in
SQLite.

| provider | how | used for |
|---|---|---|
| `queue` (default) | a cache miss is queued; `python -m tally.llm export` writes prompts to `data/queue/`; Claude Sonnet agents answered them; `python -m tally.llm import` validates and stores | every answer in the committed cache |
| `gemini` | `LLM_PROVIDER_TALLY=gemini` + `GEMINI_API_KEY` in `.env` (see `.env.example`), or `GEMINI_API_KEYS=k1,k2` to rotate keys; live `google-genai` call with the same prompt and JSON schema | production / new uploads; the §11 re-run |

The cache key includes the model name, so switching to Gemini re-runs extraction rather than mixing answers from two
models. Both models' answers are committed. To redo the Gemini run live:
`LLM_PROVIDER_TALLY=gemini TALLY_RESULTS=results/gemini python -m tally.warm --workers 6`, then
`make reproduce-gemini compare`. `TALLY_OFFLINE=1` makes the Gemini provider cache-only.

## Layout

```
config.yaml            data, policy weights, thresholds (single source of truth)
tally/
  prep.py              Kaggle CSVs -> masked subsample (12 jobs, 295 resumes) in data/work/
  clean.py             unicode / invisible chars / PII masking / injection regex
  schemas.py prompts.py llm.py store.py   LLM contract, prompts, provider + cache, SQLite
  retrieve.py          passage splitting + BM25 with a finance synonym list
  experience.py        years from role dates ("Current" = the resume's own latest date)
  screen.py            checklist -> grade -> score -> lane -> explanation; CLI
  golden.py            golden-pair sampling + blind labelling packets
  evaluate.py          threshold tuning (dev), metrics, baselines, extraction
  robust.py            fairness swaps + manipulation tests
  judge.py             LLM-as-judge and agreement with the reviewer
  warm.py compare.py   parallel cache fill for a live provider; Sonnet-vs-Gemini comparison
web/app.py, web/static/   Flask JSON API + one Tailwind/vanilla-JS page
golden/                rubric, pairs, human labels (+ Sonnet draft), JD + extraction gold, explanation ratings
results/               every JSON the report cites (results/gemini/ = Gemini 3.5-flash-lite, results/gemini_3.1_flash_lite/ = earlier Gemini run)
```

## Data

* **Resumes**: Kaggle *snehaanbhawal/resume-dataset* (`Resume.csv`). All ACCOUNTANT and FINANCE resumes, plus
  10 each from BANKING, CONSULTANT, BUSINESS-DEVELOPMENT and SALES, plus 20 random others: 295 after removing 1
  duplicate. Contact details are masked (emails, phones, URLs, street addresses, IDs). The dataset already replaces
  names, companies and cities with placeholders.
* **Jobs**: Kaggle *arshkon/linkedin-job-postings* (`postings.csv`). One posting per role slot (staff accountant,
  senior accountant, AP, AR, tax, financial analyst, FP&A, controller, internal audit, payroll, cost accountant,
  accounting manager), picked by title pattern, 300–900 words, seeded random choice. See `data/work/manifest.json`.
* To rebuild from raw: put the two CSVs in `data/raw/`, then run `make prep sample`.
* No synthetic resumes are in the evaluation set. The fairness and manipulation suites edit real resumes, and those
  edits are labelled as synthetic in `results/`.

## Credits and AI use

* Datasets: Kaggle snehaanbhawal/resume-dataset and arshkon/linkedin-job-postings.
* Built with Claude Code as a coding assistant. LLM answers in the committed cache come from Claude Sonnet agents and
  from `gemini-3.5-flash-lite` (production setting) and `gemini-3.1-flash-lite` (see above).
* **Golden labels** (`golden/labels.csv`, 180 pairs) were written by a person, blind, from the text packets in
  `golden/packets/`. An earlier blind Claude Sonnet draft is kept as a second rater (`golden/labels_sonnet_draft.csv`;
  agreement in `results/label_agreement.json`). The JD gold, the extraction gold and the 30 explanation ratings were
  drafted by Claude Sonnet and are still to be reviewed (REPORT §6, §7).
* Libraries: Flask, pandas, pydantic, rank-bm25, rapidfuzz, scikit-learn, scipy, google-genai, Tailwind CSS (browser
  build via jsDelivr), IBM Plex fonts (Google Fonts).
