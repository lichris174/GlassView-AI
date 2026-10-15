"""Deterministic scoring of an answer against a case's criteria.

Each criterion is a hard pass/fail; a case passes only when every criterion it
declares is satisfied. Matching is case-insensitive substring (plus optional
regex), which is cheap, reproducible, and good enough to catch regressions
without a model-graded judge. An LLM-judge criterion can slot in later behind
the same CaseResult shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cases import EvalCase


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    checks: list[Check]
    answer: str

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def score(self) -> float:
        return sum(c.passed for c in self.checks) / len(self.checks) if self.checks else 1.0


def score_case(case: EvalCase, answer: str) -> CaseResult:
    text = answer.lower()
    checks: list[Check] = []

    for term in case.contains_all:
        checks.append(
            Check(f"contains '{term}'", term.lower() in text)
        )

    if case.contains_any:
        hit = next((t for t in case.contains_any if t.lower() in text), None)
        checks.append(
            Check(
                f"contains any of {case.contains_any}",
                hit is not None,
                f"matched '{hit}'" if hit else "no term matched",
            )
        )

    for term in case.not_contains:
        present = term.lower() in text
        checks.append(Check(f"omits '{term}'", not present))

    if case.regex:
        checks.append(
            Check(f"matches /{case.regex}/", re.search(case.regex, answer) is not None)
        )

    if not checks:
        # A case with no criteria only asserts that a non-empty answer came back.
        checks.append(Check("non-empty answer", bool(answer.strip())))

    return CaseResult(case_id=case.id, checks=checks, answer=answer)
