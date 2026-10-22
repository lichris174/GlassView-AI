"""Tool registry: name -> callable plus a description the model can read."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolFn = Callable[..., Any] | Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: ToolFn

    async def call(self, **kwargs: Any) -> Any:
        result = self.fn(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str) -> Callable[[ToolFn], ToolFn]:
        def deco(fn: ToolFn) -> ToolFn:
            self.add(Tool(name=name, description=description, fn=fn))
            return fn

        return deco

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> str:
        """A compact tool catalogue for the system prompt."""
        return "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())
