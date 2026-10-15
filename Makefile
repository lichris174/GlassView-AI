# Dev tasks for the AI service. On Windows, run `make` under Git Bash, or call
# the underlying commands directly (see each recipe).
PY := .venv/Scripts/python.exe

.PHONY: test lint eval split verify-split

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check glassview_ai ml tests

# Live eval against Ollama; exits non-zero if the pass rate drops below 100%.
eval:
	$(PY) -m glassview_ai.evals.runner --threshold 1.0

# Dataset: assign capture sessions to train/val/test (test is frozen on first run).
split:
	$(PY) -m ml.splits assign

# Fails if any frozen test frame was added, removed, or modified.
verify-split:
	$(PY) -m ml.splits verify
