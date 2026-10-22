"""The concrete tools the agent loop can call.

Kept separate from :mod:`registry` (mechanism) and :mod:`loop` (control flow) so
the tool set is the only thing that changes as the assistant grows. Every tool
here is local and read-only: the agent can look things up, never mutate state.
"""

from __future__ import annotations

import asyncio

from ..db import ChatStore
from ..rag import MemoryStore
from .registry import ToolRegistry

_SNIPPET_CHARS = 300
# Upper bounds on the size args. The model picks these values, so they are
# clamped rather than trusted (sqlite-vec errors past k=4096).
_MAX_RECALL_K = 10
_MAX_CHAT_LIMIT = 20


def _clamp(value: int | str, high: int) -> int:
    return max(1, min(int(value), high))


def build_registry(memory: MemoryStore, store: ChatStore) -> ToolRegistry:
    """Build the tool registry bound to this process's memory + chat store."""
    registry = ToolRegistry()

    @registry.register(
        "recall_memory",
        'Search notes remembered from past turns. args: {"query": "<text>"} '
        "-> matching notes, most relevant first.",
    )
    async def recall_memory(query: str, k: int = 3) -> str:
        # Sync sqlite under the hood: keep it off the event loop.
        hits = await asyncio.to_thread(memory.query, query, k=_clamp(k, _MAX_RECALL_K))
        if not hits:
            return "no matching memories"
        return "\n".join(
            f"- {' '.join(h.text.split())[:_SNIPPET_CHARS]}" for h in hits
        )

    @registry.register(
        "list_recent_chats",
        'List the most recently updated chats. args: {"limit": 5} '
        "-> titles with message counts.",
    )
    async def list_recent_chats(limit: int = 5) -> str:
        chats = await store.list_chats()
        if not chats:
            return "no chats yet"
        return "\n".join(
            f"- {c['title']} ({c['message_count']} messages, updated {c['updated_at']})"
            for c in chats[: _clamp(limit, _MAX_CHAT_LIMIT)]
        )

    return registry
