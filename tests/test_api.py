"""Core-loop tests: CRUD + streaming chat with a faked Ollama (no network)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from glassview_ai import config
from glassview_ai.ollama_client import OllamaClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TestClient]:
    # Isolate the DB and avoid touching a real Ollama daemon.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("GLASSVIEW_DB", tmp.name)
    monkeypatch.setattr(config, "detect_model", lambda *a, **k: "fake-vl:test")

    async def fake_stream(self, messages, *, temperature=0.2):  # noqa: ANN001
        for tok in ["Hello", " ", "world"]:
            yield tok

    monkeypatch.setattr(OllamaClient, "stream_chat", fake_stream)

    # Import here so monkeypatched config is in effect for the lifespan.
    from glassview_ai.main import app

    with TestClient(app) as c:
        yield c
    os.unlink(tmp.name)
    mem = f"{tmp.name}.memories.db"
    if os.path.exists(mem):
        os.unlink(mem)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["model"] == "fake-vl:test"


def test_chat_crud(client: TestClient) -> None:
    r = client.post("/chats", json={"title": "First"})
    cid = r.json()["chat"]["id"]
    assert client.get("/chats").json()["chats"]

    r = client.patch(f"/chats/{cid}", json={"title": "Renamed"})
    assert r.status_code == 200
    assert client.get(f"/chats/{cid}").json()["title"] == "Renamed"

    assert client.delete(f"/chats/{cid}").status_code == 200
    assert client.get(f"/chats/{cid}").status_code == 404


def test_streaming_chat_persists(client: TestClient) -> None:
    cid = "chat_test_1"
    with client.stream("POST", "/chat", json={"chat_id": cid, "message": "hi"}) as r:
        body = "".join(chunk for chunk in r.iter_text())
    assert body == "Hello world"

    # The turn is persisted: user + assistant, and title derives from first message.
    detail = client.get(f"/chats/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "Hello world"
    assert detail["title"] == "hi"


def test_chat_turn_is_recalled(client: TestClient) -> None:
    """A completed turn lands in memory and is retrievable via /recall."""
    cid = "chat_recall_1"
    with client.stream(
        "POST", "/chat",
        json={"chat_id": cid, "message": "why is postgres refusing connections"},
    ) as r:
        "".join(r.iter_text())

    hits = client.get("/recall", params={"q": "postgres connection", "k": 3}).json()["hits"]
    assert hits
    assert "postgres" in hits[0]["text"].lower()
    assert hits[0]["meta"]["chat_id"] == cid


def test_recall_is_injected_from_other_chats(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory from another chat reaches the prompt; the same chat's does not."""
    # Seed a memory under a different chat id.
    with client.stream(
        "POST", "/chat",
        json={"chat_id": "chat_seed", "message": "the deploy fails with ECONNREFUSED 5432"},
    ) as r:
        "".join(r.iter_text())

    seen: list[list[dict]] = []

    async def capture(self, messages, *, temperature=0.2):  # noqa: ANN001
        seen.append(messages)
        yield "ok"

    monkeypatch.setattr(OllamaClient, "stream_chat", capture)

    with client.stream(
        "POST", "/chat",
        json={"chat_id": "chat_asking", "message": "why ECONNREFUSED 5432 on deploy"},
    ) as r:
        "".join(r.iter_text())

    prompt = seen[-1][-1]["content"]
    assert "recalled from earlier sessions" in prompt
    assert "5432" in prompt


def test_recall_can_be_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client.stream(
        "POST", "/chat",
        json={"chat_id": "chat_seed2", "message": "the deploy fails with ECONNREFUSED 5432"},
    ) as r:
        "".join(r.iter_text())

    seen: list[list[dict]] = []

    async def capture(self, messages, *, temperature=0.2):  # noqa: ANN001
        seen.append(messages)
        yield "ok"

    monkeypatch.setattr(OllamaClient, "stream_chat", capture)

    with client.stream(
        "POST", "/chat",
        json={
            "chat_id": "chat_asking2",
            "message": "why ECONNREFUSED 5432 on deploy",
            "recall": False,
        },
    ) as r:
        "".join(r.iter_text())

    assert "recalled from earlier sessions" not in seen[-1][-1]["content"]


def test_redaction_defaults_on_and_can_be_disabled(client: TestClient) -> None:
    """Secrets are masked in memory by default; redact=false stores them raw."""
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"

    with client.stream(
        "POST", "/chat",
        json={"chat_id": "chat_redacted", "message": f"is my token {secret} leaked"},
    ) as r:
        "".join(r.iter_text())

    hits = client.get("/recall", params={"q": "token leaked", "k": 5}).json()["hits"]
    stored = " ".join(h["text"] for h in hits)
    assert secret not in stored
    assert "[REDACTED:GITHUB_TOKEN]" in stored

    with client.stream(
        "POST", "/chat",
        json={
            "chat_id": "chat_raw",
            "message": f"is my token {secret} leaked",
            "redact": False,
        },
    ) as r:
        "".join(r.iter_text())

    hits = client.get("/recall", params={"q": "token leaked", "k": 5}).json()["hits"]
    assert secret in " ".join(h["text"] for h in hits)


def test_agent_runs_tools_and_reports_steps(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent loop is reachable over HTTP and its tools actually execute."""
    # Seed a memory the agent can look up.
    with client.stream(
        "POST", "/chat",
        json={"chat_id": "chat_for_agent", "message": "the printer jams on duplex jobs"},
    ) as r:
        "".join(r.iter_text())

    replies = iter([
        '{"tool": "recall_memory", "args": {"query": "printer"}}',
        '{"final": "It jams on duplex jobs."}',
    ])

    async def scripted(self, messages, *, temperature=0.2):  # noqa: ANN001
        yield next(replies)

    monkeypatch.setattr(OllamaClient, "stream_chat", scripted)

    body = client.post("/agent", json={"question": "what is wrong with the printer"}).json()
    assert body["answer"] == "It jams on duplex jobs."
    assert body["stopped_reason"] == "final"
    assert [s["tool"] for s in body["steps"]] == ["recall_memory"]
    assert "printer" in body["steps"][0]["observation"]
    assert "recall_memory" in body["tools"]


def test_agent_reports_unknown_tool_without_crashing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = iter([
        '{"tool": "rm_rf", "args": {}}',
        '{"final": "no such tool"}',
    ])

    async def scripted(self, messages, *, temperature=0.2):  # noqa: ANN001
        yield next(replies)

    monkeypatch.setattr(OllamaClient, "stream_chat", scripted)

    body = client.post("/agent", json={"question": "delete everything"}).json()
    assert "unknown tool" in body["steps"][0]["observation"]
    assert body["answer"] == "no such tool"


def test_stream_error_is_surfaced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Ollama failure mid-stream must reach the client, not vanish as an
    empty 200 body, and the failed turn must still be recorded."""

    async def boom(self, messages, *, temperature=0.2):  # noqa: ANN001
        raise RuntimeError("Ollama HTTP 404: model not found")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(OllamaClient, "stream_chat", boom)

    cid = "chat_err_1"
    with client.stream("POST", "/chat", json={"chat_id": cid, "message": "hi"}) as r:
        body = "".join(chunk for chunk in r.iter_text())
    assert "[error]" in body
    assert "404" in body

    detail = client.get(f"/chats/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert "[error]" in detail["messages"][1]["content"]


def test_agent_reports_model_failure_as_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upstream model failure is a bad gateway, not an opaque 500."""

    async def boom(self, messages, *, temperature=0.2):  # noqa: ANN001
        raise RuntimeError("Ollama HTTP 500: model requires more system memory")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(OllamaClient, "stream_chat", boom)

    r = client.post("/agent", json={"question": "anything"})
    assert r.status_code == 502
    assert "more system memory" in r.json()["detail"]


def test_chat_dispatches_to_a_cloud_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider + key routes the turn away from Ollama, and the key is not stored."""
    import glassview_ai.main as main_mod

    seen: dict = {}

    class FakeCloud:
        model = "gpt-4o-mini"

        async def stream_chat(self, messages, *, temperature=0.2):  # noqa: ANN001
            seen["messages"] = messages
            yield "cloud says hi"

    def fake_build(provider, *, api_key, model, ollama_host, ollama_model):  # noqa: ANN001
        seen["provider"] = provider
        seen["api_key"] = api_key
        return FakeCloud()

    monkeypatch.setattr(main_mod, "build_client", fake_build)

    with client.stream(
        "POST", "/chat",
        json={
            "chat_id": "chat_cloud",
            "message": "hello",
            "provider": "openai",
            "api_key": "sk-secret-key-value",
        },
    ) as r:
        body = "".join(r.iter_text())

    assert body == "cloud says hi"
    assert seen["provider"] == "openai"

    # The turn is recorded against the cloud model, and the key never lands in
    # the transcript or in memory.
    detail = client.get("/chats/chat_cloud").json()
    assert "sk-secret-key-value" not in str(detail)
    hits = client.get("/recall", params={"q": "hello", "k": 5}).json()["hits"]
    assert "sk-secret-key-value" not in str(hits)


def test_cloud_provider_without_key_is_a_400(client: TestClient) -> None:
    r = client.post("/chat", json={"chat_id": "chat_nokey", "message": "hi",
                                   "provider": "anthropic"})
    assert r.status_code == 400
    assert "API key" in r.json()["detail"]


def test_health_advertises_providers(client: TestClient) -> None:
    providers = client.get("/health").json()["providers"]
    assert set(providers) == {"ollama", "openai", "anthropic", "deepseek"}
