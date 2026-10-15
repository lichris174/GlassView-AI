"""Thin async Ollama client: streaming chat with an image-aware message shape."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


def _strip_data_url(image: str) -> str:
    """Accept a data URL or bare base64; return bare base64."""
    return image.split(",", 1)[1] if "," in image else image


def build_messages(
    system_prompt: str,
    history: list[dict[str, Any]],
    user_message: str,
    image: str | None,
) -> list[dict[str, Any]]:
    """Assemble the Ollama /api/chat message list from stored history + new turn."""
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for h in history:
        entry: dict[str, Any] = {"role": h["role"], "content": h["content"]}
        if h.get("images"):
            entry["images"] = [_strip_data_url(i) for i in h["images"]]
        msgs.append(entry)

    user: dict[str, Any] = {
        "role": "user",
        "content": (user_message or "").strip() or "Describe this screenshot briefly.",
    }
    if image:
        user["images"] = [_strip_data_url(image)]
    msgs.append(user)
    return msgs


class OllamaClient:
    def __init__(self, host: str, model: str) -> None:
        self.host = host
        self.model = model

    async def stream_chat(
        self, messages: list[dict[str, Any]], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        """Yield response text chunks as they arrive from Ollama."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "top_p": 0.9, "num_predict": -1},
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise RuntimeError(f"Ollama HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = (obj.get("message") or {}).get("content") or obj.get("response")
                    if chunk:
                        yield chunk
