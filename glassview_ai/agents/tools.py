"""The concrete tools the agent loop can call.

Kept separate from :mod:`registry` (mechanism) and :mod:`loop` (control flow) so
the tool set is the only thing that changes as the assistant grows. Every tool
here is local and read-only: the agent can look things up, never mutate state.
"""

from __future__ import annotations

from ..db import ChatStore
from ..rag import MemoryStore
from .registry import ToolRegistry

_SNIPPET_CHARS = 300


def build_registry(memory: MemoryStore, store: ChatStore) -> ToolRegistry:
    """Build the tool registry bound to this process's memory + chat store."""
    registry = ToolRegistry()

    @registry.register(
        "recall_memory",
        'Search notes remembered from past turns. args: {"query": "<text>"} '
        "-> matching notes, most relevant first.",
    )
    def recall_memory(query: str, k: int = 3) -> str:
        hits = memory.query(query, k=int(k))
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
            for c in chats[: int(limit)]
        )

    return registry
