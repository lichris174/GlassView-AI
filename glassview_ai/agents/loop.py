"""The agent loop itself: parse model output, run tools, bound the steps."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .registry import ToolRegistry

# ``complete`` takes the running transcript and returns the next model message.
CompleteFn = Callable[[list[dict[str, str]]], Awaitable[str]]


@dataclass(frozen=True)
class AgentStep:
    tool: str
    args: dict[str, Any]
    observation: str


@dataclass(frozen=True)
class AgentResult:
    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    stopped_reason: str = "final"


# Bounds on the embedded-object scan. Model output is untrusted, and decoding at
# every "{" of a long reply is quadratic, so only the first few candidates in
# the first stretch of text are tried; a tool call buried past that is treated
# as a plain answer.
_MAX_SCAN_CHARS = 20_000
_MAX_CANDIDATES = 32

_DECODER = json.JSONDecoder()


def _decode(text: str, start: int = 0) -> Any:
    """Decode one JSON value at ``text[start]``, or None if there is none.

    RecursionError is caught alongside ValueError: a deeply nested reply
    ("[[[[..." ) overflows the decoder rather than failing cleanly.
    """
    try:
        return _DECODER.raw_decode(text, start)[0]
    except (ValueError, RecursionError):
        return None


def _is_protocol(obj: Any) -> bool:
    return isinstance(obj, dict) and ("tool" in obj or "final" in obj)


def _parse(output: str) -> dict[str, Any] | None:
    """Pull the tool-call / final-answer object out of a model message, if any.

    The whole reply is tried first, so a ``final`` whose text contains braces
    parses intact. Otherwise the first embedded object carrying a ``tool`` or
    ``final`` key wins; any other JSON (a code sample in a prose answer) is not
    protocol, so the reply is treated as a plain answer.
    """
    try:
        whole = json.loads(output.strip())
    except (ValueError, RecursionError):
        whole = None
    if _is_protocol(whole):
        return whole
    text = output[:_MAX_SCAN_CHARS]
    start = text.find("{")
    for _ in range(_MAX_CANDIDATES):
        if start == -1:
            break
        obj = _decode(text, start)
        if _is_protocol(obj):
            return obj
        start = text.find("{", start + 1)
    return None


async def run_agent(
    question: str,
    complete: CompleteFn,
    registry: ToolRegistry,
    *,
    system_prompt: str = "",
    max_steps: int = 4,
) -> AgentResult:
    """Drive the tool-use loop.

    The model should reply with either ``{"tool": "<name>", "args": {...}}`` to
    call a tool or ``{"final": "<answer>"}`` to finish. Free-text replies with
    no JSON are treated as the final answer, so a model that just answers still
    works.
    """
    catalogue = registry.describe()
    sys = (
        f"{system_prompt}\n\nYou may use tools. Available tools:\n{catalogue}\n\n"
        'To call a tool reply ONLY with {"tool": "name", "args": {...}}. '
        'When you can answer, reply with {"final": "your answer"}.'
    ).strip()

    transcript: list[dict[str, str]] = [
        {"role": "system", "content": sys},
        {"role": "user", "content": question},
    ]
    steps: list[AgentStep] = []

    for _ in range(max_steps):
        output = await complete(transcript)
        parsed = _parse(output)

        if parsed is None:
            return AgentResult(answer=output.strip(), steps=steps)

        # Model output is untrusted: a malformed reply becomes an error step the
        # model can correct, never an exception that escapes the loop.
        name = parsed.get("tool")
        raw_args = parsed.get("args") or {}
        args = raw_args if isinstance(raw_args, dict) else {}
        # A null "final" next to a tool call is just the model filling in both
        # keys; run the tool rather than treating it as a malformed answer.
        if "final" in parsed and (parsed["final"] is not None or "tool" not in parsed):
            final = parsed["final"]
            if isinstance(final, str):
                return AgentResult(answer=final, steps=steps)
            if final is not None:
                return AgentResult(answer=json.dumps(final, ensure_ascii=False), steps=steps)
            name, observation = "final", 'error: "final" must be the answer text'
        elif not isinstance(name, str):
            observation = f'error: "tool" must be a tool name, got {name!r}'
        elif not isinstance(raw_args, dict):
            observation = 'error: "args" must be a JSON object'
        elif (tool := registry.get(name)) is None:
            observation = f"error: unknown tool {name!r}"
        else:
            try:
                observation = str(await tool.call(**args))
            except Exception as exc:  # noqa: BLE001 - surface tool failure to the model
                observation = f"error: {exc}"

        steps.append(AgentStep(tool=str(name), args=args, observation=observation))
        transcript.append({"role": "assistant", "content": output})
        transcript.append({"role": "user", "content": f"Observation: {observation}"})

    return AgentResult(
        answer="(stopped: step budget reached)",
        steps=steps,
        stopped_reason="max_steps",
    )
