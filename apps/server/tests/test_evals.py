"""Eval harness tests: scorer logic, the golden set loads + scores, and the
runner aggregates pass rate against a threshold. All offline (fake answers)."""

from __future__ import annotations

import pytest

from glassview_ai.evals import EvalCase, load_cases, run_eval, score_case


def test_score_contains_all_and_not_contains() -> None:
    case = EvalCase(
        id="t1",
        question="q",
        contains_all=["5432", "postgres"],
        not_contains=["as an ai"],
    )
    good = score_case(case, "Postgres is not listening on port 5432.")
    assert good.passed and good.score == 1.0

    bad = score_case(case, "As an AI, port 5432 looks closed.")
    assert not bad.passed  # missing 'postgres' and contains the banned phrase


def test_score_contains_any_and_regex() -> None:
    case = EvalCase(id="t2", question="q", contains_any=["400", "401"], regex=r"\d+\.")
    assert score_case(case, "1. A 401 is unauthorized.").passed
    assert not score_case(case, "Some prose with 401 but no list marker").passed


def test_empty_criteria_requires_nonempty_answer() -> None:
    case = EvalCase(id="t3", question="q")
    assert score_case(case, "anything").passed
    assert not score_case(case, "   ").passed


def test_golden_set_loads_and_is_well_formed() -> None:
    cases = load_cases()
    assert cases, "golden set should not be empty"
    assert all(c.id and c.question for c in cases)


@pytest.mark.asyncio
async def test_run_eval_pass_rate_and_threshold() -> None:
    cases = [
        EvalCase(id="a", question="q", contains_all=["yes"]),
        EvalCase(id="b", question="q", contains_all=["never"]),
    ]

    async def answer_fn(case: EvalCase) -> str:
        return "yes" if case.id == "a" else "nope"

    report = await run_eval(cases, answer_fn, threshold=1.0)
    assert report.pass_rate == 0.5
    assert not report.passed  # one case fails, threshold is 100%

    lenient = await run_eval(cases, answer_fn, threshold=0.5)
    assert lenient.passed
    assert "pass rate" in lenient.render()


@pytest.mark.asyncio
async def test_run_eval_treats_raised_call_as_failed_case() -> None:
    async def boom(case: EvalCase) -> str:
        raise RuntimeError("model down")

    report = await run_eval([EvalCase(id="x", question="q", contains_all=["ok"])], boom)
    assert not report.passed
    assert "[error] model down" in report.results[0].answer
