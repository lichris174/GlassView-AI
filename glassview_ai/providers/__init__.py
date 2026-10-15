"""Provider dispatch: pick the backend that answers a turn.

Local Ollama remains the default and the only one that needs no credentials.
A cloud provider is selected per-request by the frontend, which sends the key
the user typed into Settings. Keys are used for the one call and never
persisted, logged, or written to memory.
"""

from __future__ import annotations

from typing import Literal

from ..ollama_client import OllamaClient
from .base import ChatClient, MissingApiKeyError, media_type, split_system

Provider = Literal["ollama", "openai", "anthropic", "deepseek"]

PROVIDERS: tuple[str, ...] = ("ollama", "openai", "anthropic", "deepseek")


def detect_provider(api_key: str | None) -> Provider:
    """Infer the provider from an API key's prefix.

    Mirrors the frontend's ``detectProvider`` so the backend never depends on
    the client having classified the key correctly. Anthropic is checked first
    because ``sk-ant-`` also matches the OpenAI ``sk-`` prefix.

    DeepSeek is *not* inferable: its keys use the same ``sk-`` prefix as
    OpenAI's, so it is only ever reached by an explicit provider choice.
    """
    if not api_key:
        return "ollama"
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("sk-"):
        return "openai"
    return "ollama"


def build_client(
    provider: str | None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    ollama_host: str,
    ollama_model: str,
) -> ChatClient:
    """Build the client for this turn.

    An unknown or absent provider falls back to local Ollama rather than
    erroring: losing the local path because of a bad string would be worse than
    ignoring it.
    """
    resolved = provider if provider in PROVIDERS else detect_provider(api_key)

    if resolved == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(api_key, model)
    if resolved == "openai":
        from .openai_client import OpenAIClient

        return OpenAIClient(api_key, model)
    if resolved == "deepseek":
        from .openai_client import DeepSeekClient

        return DeepSeekClient(api_key, model)
    return OllamaClient(ollama_host, model or ollama_model)


__all__ = [
    "ChatClient",
    "MissingApiKeyError",
    "PROVIDERS",
    "Provider",
    "build_client",
    "detect_provider",
    "media_type",
    "split_system",
]
