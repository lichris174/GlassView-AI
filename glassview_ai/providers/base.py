"""Shared plumbing for provider clients.

Every provider consumes the same internal message shape that
:func:`glassview_ai.ollama_client.build_messages` produces::

    [{"role": "system"|"user"|"assistant", "content": str, "images": [b64, ...]}]

and yields plain text chunks. Each provider module owns the translation from
that shape into its own wire format, so the chat path never branches on
provider beyond picking a client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChatClient(Protocol):
    """What ``/chat`` needs from any backend."""

    model: str

    def stream_chat(
        self, messages: list[dict[str, Any]], *, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...


class MissingApiKeyError(ValueError):
    """A cloud provider was selected without a key to authenticate with."""


# Base64 payload prefixes for the formats a screen capture or attachment can be.
# Cheaper and more reliable than trusting a data-URL header the client may have
# stripped, and both cloud APIs require an explicit media type.
_MAGIC: tuple[tuple[str, str], ...] = (
    ("iVBORw0KGgo", "image/png"),
    ("/9j/", "image/jpeg"),
    ("R0lGOD", "image/gif"),
    ("UklGR", "image/webp"),
)

DEFAULT_MEDIA_TYPE = "image/png"


def media_type(b64: str) -> str:
    """Sniff an image's media type from its base64 payload."""
    for prefix, mime in _MAGIC:
        if b64.startswith(prefix):
            return mime
    return DEFAULT_MEDIA_TYPE


def split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Split the leading system message out from the conversation.

    Anthropic takes the system prompt as a top-level parameter rather than a
    message, and OpenAI is happy either way, so both providers start here.
    """
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return "\n\n".join(p for p in system_parts if p), rest
