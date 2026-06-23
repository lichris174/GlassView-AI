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
