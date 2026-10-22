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


async def _run_scripted(replies: list[str], reg: ToolRegistry | None = None):  # noqa: ANN202
    scripted = iter(replies)

    async def complete(_transcript):
        return next(scripted)

    return await run_agent("q", complete, reg or _registry())


@pytest.mark.parametrize(
    "reply",
    [
        '{"tool": "add", "args": [1, 2]}',
        '{"tool": "add", "args": "1 2"}',
        '{"tool": 3, "args": {}}',
        '{"tool": null}',
    ],
)
async def test_malformed_tool_call_becomes_an_error_step(reply: str) -> None:
    result = await _run_scripted([reply, '{"final": "ok"}'])
    assert result.answer == "ok"
    step = result.steps[0]
    assert step.observation.startswith("error:")
    assert isinstance(step.args, dict) and isinstance(step.tool, str)


async def test_non_string_final_is_coerced_to_text() -> None:
    assert (await _run_scripted(['{"final": 42}'])).answer == "42"
    assert (await _run_scripted(['{"final": {"a": 1}}'])).answer == '{"a": 1}'


async def test_null_final_is_an_error_step() -> None:
    result = await _run_scripted(['{"final": null}', '{"final": "ok"}'])
    assert result.answer == "ok"
    assert result.steps[0].observation.startswith("error:")


async def test_plain_answer_containing_json_is_final() -> None:
    """A JSON sample inside a prose answer is not a tool call."""
    reply = 'Use a config like {"retries": 3, "timeout": 5} and restart.'
    result = await _run_scripted([reply])
    assert result.answer == reply
    assert result.steps == []


async def test_tool_call_after_an_unrelated_json_sample_is_found() -> None:
    reply = 'Example {"x": 1}. {"tool": "add", "args": {"a": 2, "b": 3}}'
    result = await _run_scripted([reply, '{"final": "5"}'])
    assert [s.tool for s in result.steps] == ["add"]
    assert result.steps[0].observation == "5"


async def test_whole_reply_json_is_preferred() -> None:
    result = await _run_scripted(['  {"final": "has {braces} inside"}  '])
    assert result.answer == "has {braces} inside"


async def test_builtin_tools_bound_their_size_args() -> None:
    from glassview_ai.agents.tools import build_registry
    from glassview_ai.rag import MemoryStore

    class FakeChats:
        async def list_chats(self) -> list[dict]:
            return [
                {"title": f"c{i}", "message_count": 1, "updated_at": "t"} for i in range(100)
            ]

    memory = MemoryStore()
    memory.add("printer jams on duplex")
    reg = build_registry(memory, FakeChats())  # type: ignore[arg-type]
    try:
        recall = await reg.get("recall_memory").call(query="printer", k=100000)
        assert not recall.startswith("error") and "printer" in recall
        listed = await reg.get("list_recent_chats").call(limit=100000)
        assert 0 < listed.count("\n") + 1 <= 20
        assert (await reg.get("list_recent_chats").call(limit=-5)).count("\n") == 0
    finally:
        memory.close()


async def test_tool_with_null_final_runs_the_tool() -> None:
    reply = '{"tool": "add", "args": {"a": 1, "b": 2}, "final": null}'
    result = await _run_scripted([reply, '{"final": "3"}'])
    assert [s.tool for s in result.steps] == ["add"]
    assert result.steps[0].observation == "3"


def test_parse_is_linear_on_many_stray_braces() -> None:
    import time

    from glassview_ai.agents.loop import _parse

    t0 = time.perf_counter()
    assert _parse("x{" * 20000) is None
    assert time.perf_counter() - t0 < 1.0


@pytest.mark.parametrize(
    ("prefix", "unit"), [("", "["), ("", '{"a":'), ('say {"final": ', "[")]
)
async def test_deeply_nested_reply_is_a_plain_answer(prefix: str, unit: str) -> None:
    reply = prefix + unit * 100000
    result = await _run_scripted([reply])
    assert result.answer == reply.strip()
    assert result.steps == []
