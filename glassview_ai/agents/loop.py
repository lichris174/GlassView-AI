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


def _extract_json_block(output: str) -> str | None:
    """Return the first balanced JSON object literal found in ``output``."""
    start = output.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(output[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return output[start : i + 1]
    return None


def _parse(output: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model message, if any."""
    block = _extract_json_block(output)
    if block is None:
        return None
    try:
        obj = json.loads(block)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


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

        if parsed is None or "final" in parsed:
            answer = parsed["final"] if parsed and "final" in parsed else output.strip()
            return AgentResult(answer=answer, steps=steps)

        name = parsed.get("tool")
        args = parsed.get("args") or {}
        tool = registry.get(name) if isinstance(name, str) else None
        if tool is None:
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
