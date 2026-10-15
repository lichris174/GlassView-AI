"""Anthropic provider, via the official ``anthropic`` SDK.

Notes that are easy to get wrong and expensive to rediscover:

* **No sampling parameters.** ``temperature`` / ``top_p`` / ``top_k`` are
  rejected with a 400 on Claude Opus 5 and the rest of the 4.6+ family, so the
  ``temperature`` argument in the shared interface is accepted and ignored here
  rather than forwarded.
* **System prompt is a parameter**, not a message (see ``split_system``).
* **Images are content blocks** with an explicit ``media_type``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .base import MissingApiKeyError, media_type, split_system

# Anthropic's current flagship. Overridable per-request via ChatRequest.model.
DEFAULT_MODEL = "claude-opus-5"

# Generous ceiling, not a target: it caps a runaway answer without truncating a
# normal one. Streaming keeps a high ceiling from risking an HTTP timeout.
MAX_TOKENS = 16000


def to_anthropic(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Convert internal messages to (system, Anthropic messages)."""
    system, rest = split_system(messages)
    out: list[dict[str, Any]] = []
    for m in rest:
        blocks: list[dict[str, Any]] = []
        for img in m.get("images") or []:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type(img),
                        "data": img,
                    },
                }
            )
        # The text block goes last so the image is the thing being asked about.
        if m.get("content"):
            blocks.append({"type": "text", "text": m["content"]})
        if blocks:
            out.append({"role": m["role"], "content": blocks})
    return system, out


class AnthropicClient:
    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        if not api_key:
            raise MissingApiKeyError("Anthropic selected but no API key was supplied")
        # Imported lazily so the dependency is only needed by users who pick
        # this provider; Ollama-only installs never touch it.
        from anthropic import AsyncAnthropic

        self.model = model or DEFAULT_MODEL
        self._client = AsyncAnthropic(api_key=api_key)

    async def stream_chat(
        self, messages: list[dict[str, Any]], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        del temperature  # rejected by the API on current models; see module docstring
        system, msgs = to_anthropic(messages)
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=msgs,
        ) as stream:
            async for text in stream.text_stream:
                yield text
