# Dev tasks for the AI service. On Windows, run `make` under Git Bash, or call
# the underlying commands directly (see each recipe).
PY := .venv/Scripts/python.exe

.PHONY: test lint eval

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check glassview_ai tests

# Live eval against Ollama; exits non-zero if the pass rate drops below 100%.
eval:
	$(PY) -m glassview_ai.evals.runner --threshold 1.0
