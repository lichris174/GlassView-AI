from __future__ import annotations

import pytest

from glassview_ai.agents import ToolRegistry, run_agent


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register("recall", "look up a past memory by query")
    def recall(query: str) -> str:
        return "yesterday you saw ECONNREFUSED on port 5432"

    @reg.register("add", "add two integers a and b")
    async def add(a: int, b: int) -> int:
        return a + b

    return reg


@pytest.mark.asyncio
async def test_loop_calls_tool_then_finishes() -> None:
    reg = _registry()
    scripted = iter(
        [
            '{"tool": "recall", "args": {"query": "db error"}}',
            '{"final": "It was ECONNREFUSED on port 5432."}',
        ]
    )

    async def complete(_transcript):
        return next(scripted)

    result = await run_agent("what was that db error", complete, reg)
    assert result.answer == "It was ECONNREFUSED on port 5432."
    assert [s.tool for s in result.steps] == ["recall"]
    assert "5432" in result.steps[0].observation


@pytest.mark.asyncio
async def test_plain_text_answer_is_final() -> None:
    async def complete(_transcript):
        return "Just a direct answer, no tools."

    result = await run_agent("hi", complete, ToolRegistry())
    assert "direct answer" in result.answer
    assert result.steps == []


@pytest.mark.asyncio
async def test_unknown_tool_feeds_error_then_recovers() -> None:
    reg = _registry()
    scripted = iter(
        [
            '{"tool": "nope", "args": {}}',
            '{"final": "ok"}',
        ]
    )

    async def complete(_transcript):
        return next(scripted)

    result = await run_agent("q", complete, reg)
    assert "error: unknown tool" in result.steps[0].observation
    assert result.answer == "ok"


@pytest.mark.asyncio
async def test_step_budget_stops_loop() -> None:
    reg = _registry()

    async def complete(_transcript):
        return '{"tool": "recall", "args": {"query": "x"}}'  # never finishes

    result = await run_agent("q", complete, reg, max_steps=3)
    assert result.stopped_reason == "max_steps"
    assert len(result.steps) == 3
