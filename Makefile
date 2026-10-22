# Dev tasks for the AI service. On Windows, run `make` under Git Bash, or call
# the underlying commands directly (see each recipe).
PY := .venv/Scripts/python.exe

.PHONY: test lint eval split verify-split baselines

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check glassview_ai ml tests

# Live eval against Ollama; exits non-zero if the pass rate drops below 100%.
eval:
	$(PY) -m glassview_ai.evals.runner --threshold 1.0

# Dataset: assign capture sessions to train/val/test (test is frozen on first run).
# These are the fractions and seed the real split was frozen with (splits.json);
# ml/splits.py's own defaults (0.35/0.15, seed 0) differ. Once splits.json exists
# the flags are ignored: new sessions go to train and test/val stay fixed.
split:
	$(PY) -m ml.splits assign --test-frac 0.55 --val-frac 0.30 --seed 5

# Fails if any frozen test frame was added, removed, or modified.
verify-split:
	$(PY) -m ml.splits verify

# Baselines on a split (default val). Each run writes results/<stamp>-<system>-<split>/.
SPLIT ?= val
baselines:
	$(PY) -m ml.evaluate run --system block_all --split $(SPLIT)
	$(PY) -m ml.evaluate run --system ocr_regex --split $(SPLIT)
	$(PY) -m ml.evaluate run --system qwen_vl --split $(SPLIT)
