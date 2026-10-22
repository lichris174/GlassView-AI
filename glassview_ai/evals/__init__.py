"""Offline eval harness for the screen-copilot answer quality.

The harness is model-agnostic: it scores an answer string against per-case
criteria, and the answer is produced by an injected callable. Tests drive it
with a fake answer function (no network); ``runner.py`` wires the real Ollama
client for live evaluation and regression tracking.
"""

from typing import TYPE_CHECKING, Any

from .cases import EvalCase, load_cases
from .scorer import CaseResult, score_case

if TYPE_CHECKING:
    from .runner import EvalReport, run_eval

__all__ = [
    "EvalCase",
    "load_cases",
    "EvalReport",
    "run_eval",
    "CaseResult",
    "score_case",
]


def __getattr__(name: str) -> Any:
    # ``runner`` is imported lazily: importing it here would load it before
    # ``python -m glassview_ai.evals.runner`` executes it, which makes runpy
    # warn that the module was already in sys.modules.
    if name in ("EvalReport", "run_eval"):
        from . import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
