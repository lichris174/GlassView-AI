"""Offline eval harness for the screen-copilot answer quality.

The harness is model-agnostic: it scores an answer string against per-case
criteria, and the answer is produced by an injected callable. Tests drive it
with a fake answer function (no network); ``runner.py`` wires the real Ollama
client for live evaluation and regression tracking.
"""

from .cases import EvalCase, load_cases
from .runner import EvalReport, run_eval
from .scorer import CaseResult, score_case

__all__ = [
    "EvalCase",
    "load_cases",
    "EvalReport",
    "run_eval",
    "CaseResult",
    "score_case",
]
