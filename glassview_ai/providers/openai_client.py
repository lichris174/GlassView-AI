"""OpenAI-compatible providers over the chat-completions SSE stream.

Uses ``httpx`` rather than the ``openai`` package: the surface needed here is
one streaming POST, and it keeps the dependency footprint the same as the
Ollama client next door.

DeepSeek speaks the same chat-completions protocol, so it is the same client
pointed at a different base URL. Note that its keys also start with ``sk-``,
which is why the provider cannot be inferred from the key alone - the user
picks it explicitly in Settings.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .base import MissingApiKeyError, media_type

DEFAULT_MODEL = "gpt-4o-mini"  # vision-capable and cheap; override per request
BASE_URL = "https://api.openai.com/v1/chat/completions"

# DeepSeek: OpenAI-compatible endpoint. deepseek-chat is text-only, so images are
# dropped (see ``vision``) and an image turn reaches it as its text alone; the
# model answers without seeing the image.
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


def to_openai(
    messages: list[dict[str, Any]], *, vision: bool = True
) -> list[dict[str, Any]]:
    """Convert internal messages to OpenAI chat-completions format.

    Text-only turns keep a plain string ``content``; turns with an image use the
    multipart array with a ``data:`` URL, which is what the vision models expect.
    With ``vision=False`` images are dropped so a text-only model is never sent
    an ``image_url`` part it would reject.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        images = (m.get("images") or []) if vision else []
        if not images:
            out.append({"role": m["role"], "content": m.get("content", "")})
            continue
        parts: list[dict[str, Any]] = []
        for img in images:
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type(img)};base64,{img}"},
                }
            )
        if m.get("content"):
            parts.append({"type": "text", "text": m["content"]})
        out.append({"role": m["role"], "content": parts})
    return out


class OpenAICompatibleClient:
    """Any backend that speaks OpenAI chat-completions."""

    label = "OpenAI"
    vision = True  # whether the default model accepts image parts

    def __init__(
        self,
        api_key: str | None,
        model: str | None = None,
        *,
        base_url: str = BASE_URL,
        default_model: str = DEFAULT_MODEL,
    ) -> None:
        if not api_key:
            raise MissingApiKeyError(
                f"{self.label} selected but no API key was supplied"
            )
        self.model = model or default_model
        self._api_key = api_key
        self._base_url = base_url

    async def stream_chat(
        self, messages: list[dict[str, Any]], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": to_openai(messages, vision=self.vision),
            "stream": True,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", self._base_url, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    # The key can appear in an echoed request body; never re-raise it.
                    raise RuntimeError(
                        f"{self.label} HTTP {resp.status_code}: {body[:400]}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or [{}]
                    chunk = (choices[0].get("delta") or {}).get("content")
                    if chunk:
                        yield chunk


class OpenAIClient(OpenAICompatibleClient):
    label = "OpenAI"


class DeepSeekClient(OpenAICompatibleClient):
    label = "DeepSeek"
    vision = False

    def __init__(self, api_key: str | None, model: str | None = None) -> None:
        super().__init__(
            api_key,
            model,
            base_url=DEEPSEEK_BASE_URL,
            default_model=DEEPSEEK_DEFAULT_MODEL,
        )
