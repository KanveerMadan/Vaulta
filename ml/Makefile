# Merchant model pipeline (README.md). Every step is deterministic (common.SEED); teacher labels come from the
# committed cache, so only strings not yet labelled call the LLM (and need GROQ_API_KEY).
PY := .venv/bin/python

.PHONY: setup data label train export test retrain

setup:
	python3.12 -m venv .venv
	$(PY) -m pip install -r requirements.txt

data:
	$(PY) prepare_real.py
	$(PY) generate.py

label: data
	$(PY) teacher.py

train: label
	$(PY) train.py
	$(PY) export.py

export:
	$(PY) export.py

test:
	$(PY) -m pytest -q tests

retrain:
	$(PY) retrain.py
	$(PY) export.py
