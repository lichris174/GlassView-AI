"""Provider dispatch + wire-format conversion. No network."""

from __future__ import annotations

import pytest

from glassview_ai.ollama_client import OllamaClient
from glassview_ai.providers import MissingApiKeyError, build_client, detect_provider
from glassview_ai.providers.anthropic_client import to_anthropic
from glassview_ai.providers.base import media_type, split_system
from glassview_ai.providers.openai_client import (
    DEEPSEEK_BASE_URL,
    DeepSeekClient,
    OpenAIClient,
    to_openai,
)

PNG_B64 = "iVBORw0KGgoAAAANSUhEUg"
JPEG_B64 = "/9j/4AAQSkZJRg"

_LOCAL = {"ollama_host": "http://127.0.0.1:11434", "ollama_model": "qwen3-vl:8b"}


# --- key -> provider ---------------------------------------------------------
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (None, "ollama"),
        ("", "ollama"),
        ("sk-ant-api03-xyz", "anthropic"),
        ("sk-proj-abc", "openai"),
        ("not-a-key", "ollama"),
    ],
)
def test_detect_provider(key: str | None, expected: str) -> None:
    assert detect_provider(key) == expected


def test_deepseek_is_not_inferable_from_its_key() -> None:
    """DeepSeek keys share OpenAI's prefix, so only an explicit choice reaches it."""
    assert detect_provider("sk-deepseek-abc") == "openai"
    client = build_client("deepseek", api_key="sk-deepseek-abc", **_LOCAL)
    assert isinstance(client, DeepSeekClient)


# --- dispatch ----------------------------------------------------------------
def test_no_key_stays_local() -> None:
    client = build_client(None, **_LOCAL)
    assert isinstance(client, OllamaClient)
    assert client.model == "qwen3-vl:8b"


def test_unknown_provider_falls_back_to_local_rather_than_erroring() -> None:
    assert isinstance(build_client("gibberish", **_LOCAL), OllamaClient)


def test_cloud_provider_without_key_is_rejected() -> None:
    with pytest.raises(MissingApiKeyError):
        build_client("openai", api_key=None, **_LOCAL)
    with pytest.raises(MissingApiKeyError):
        build_client("anthropic", api_key="", **_LOCAL)


def test_model_override_is_honoured() -> None:
    client = build_client("openai", api_key="sk-x", model="gpt-4o", **_LOCAL)
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-4o"


def test_deepseek_targets_its_own_endpoint() -> None:
    client = DeepSeekClient("sk-x")
    assert client._base_url == DEEPSEEK_BASE_URL
    assert client.model == "deepseek-chat"


# --- media sniffing ----------------------------------------------------------
def test_media_type_sniffing() -> None:
    assert media_type(PNG_B64) == "image/png"
    assert media_type(JPEG_B64) == "image/jpeg"
    assert media_type("garbage") == "image/png"  # safe default


# --- wire formats ------------------------------------------------------------
def _messages() -> list[dict]:
    return [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "what is this", "images": [PNG_B64]},
        {"role": "assistant", "content": "a cat"},
    ]


def test_split_system_lifts_the_system_prompt_out() -> None:
    system, rest = split_system(_messages())
    assert system == "be terse"
    assert [m["role"] for m in rest] == ["user", "assistant"]


def test_anthropic_conversion() -> None:
    system, msgs = to_anthropic(_messages())
    assert system == "be terse"
    assert [m["role"] for m in msgs] == ["user", "assistant"]

    blocks = msgs[0]["content"]
    # Image first, then the text asking about it.
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": PNG_B64,
    }
    assert blocks[1] == {"type": "text", "text": "what is this"}


def test_openai_conversion_keeps_text_turns_as_plain_strings() -> None:
    msgs = to_openai(_messages())
    assert msgs[0] == {"role": "system", "content": "be terse"}
    assert msgs[2] == {"role": "assistant", "content": "a cat"}

    parts = msgs[1]["content"]
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"] == f"data:image/png;base64,{PNG_B64}"
    assert parts[1] == {"type": "text", "text": "what is this"}


def test_anthropic_client_ignores_temperature_signature() -> None:
    """Sampling params are rejected by the API, so the arg must not be forwarded."""
    import inspect

    from glassview_ai.providers.anthropic_client import AnthropicClient

    src = inspect.getsource(AnthropicClient.stream_chat)
    assert "del temperature" in src
    assert "temperature=temperature" not in src


async def _sent_payload(client, monkeypatch: pytest.MonkeyPatch) -> dict:  # noqa: ANN001
    """Run ``stream_chat`` against a mock transport; return the JSON it POSTed."""
    import json

    import httpx

    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        body = 'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body)

    real = httpx.AsyncClient

    def mocked(*a, **k):  # noqa: ANN002, ANN003
        return real(*a, transport=httpx.MockTransport(handler), **k)

    monkeypatch.setattr(httpx, "AsyncClient", mocked)
    chunks = [c async for c in client.stream_chat(_messages())]
    assert chunks == ["ok"]
    return sent


async def test_deepseek_is_sent_text_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """deepseek-chat is text-only: image parts must never reach its API."""
    payload = await _sent_payload(DeepSeekClient("sk-x"), monkeypatch)
    assert "image_url" not in str(payload)
    assert payload["messages"][1] == {"role": "user", "content": "what is this"}


async def test_openai_still_receives_images(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = await _sent_payload(OpenAIClient("sk-x"), monkeypatch)
    assert payload["messages"][1]["content"][0]["type"] == "image_url"
