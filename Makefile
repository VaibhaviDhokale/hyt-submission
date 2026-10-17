PY := .venv/bin/python

.PHONY: setup prep sample test app queue eval fairness adversarial judge reproduce reproduce-gemini compare report

setup:        ## Python 3.11 venv + pinned deps
	uv venv -p 3.11 .venv || python3.11 -m venv .venv
	uv pip install -p .venv -r requirements.txt || .venv/bin/pip install -r requirements.txt

prep:         ## Kaggle CSVs in data/raw/ -> masked subsample in data/work/
	$(PY) -m tally.prep

sample:       ## golden pairs + blind labelling packets
	$(PY) -m tally.golden sample

test:
	$(PY) -m pytest -q tests

app:          ## http://localhost:5057
	$(PY) -m web.app

queue:        ## what is cached / waiting for the LLM
	$(PY) -m tally.llm status

eval:         ## threshold (dev only), metrics, baselines, extraction
	$(PY) -m tally.evaluate all

fairness:
	$(PY) -m tally.robust fairness

adversarial:
	$(PY) -m tally.robust adversarial

judge:
	$(PY) -m tally.judge run
	$(PY) -m tally.judge agree

# Offline, from the committed SQLite cache and masked data: no API key, no raw data.
reproduce: test eval fairness adversarial judge

# Same suites on the Gemini answers in the cache (results/gemini/), still offline, then the cross-model table.
reproduce-gemini: export LLM_PROVIDER_TALLY=gemini
reproduce-gemini: export TALLY_RESULTS=results/gemini
reproduce-gemini: export TALLY_OFFLINE=1
reproduce-gemini: eval fairness adversarial judge

compare:          ## Sonnet vs Gemini -> results/model_comparison.json (needs both result sets)
	env -u LLM_PROVIDER_TALLY -u TALLY_RESULTS $(PY) -m tally.compare

report:           ## REPORT.tex -> REPORT.pdf (needs tectonic)
	tectonic REPORT.tex
