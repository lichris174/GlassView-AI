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

    # Loopback base URL: the app rejects any other Host header (DNS rebinding).
    with TestClient(app, base_url="http://127.0.0.1") as c:
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


# --- security: CORS allowlist + Host check -----------------------------------
def test_cors_allows_desktop_origin(client: TestClient) -> None:
    r = client.get("/chats", headers={"Origin": "http://tauri.localhost"})
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"


def test_cors_rejects_foreign_origin(client: TestClient) -> None:
    """A random website must not be able to read or delete chats."""
    r = client.get("/chats", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    preflight = client.options(
        "/chats/x",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert preflight.status_code == 400


def test_non_loopback_host_rejected(client: TestClient) -> None:
    """DNS rebinding: a hostile domain resolving to 127.0.0.1 keeps its Host."""
    r = client.get("/chats", headers={"Host": "evil.example"})
    assert r.status_code == 400


# --- Ollama down: backend still starts, local path reports why ---------------
def test_starts_and_degrades_without_ollama(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*a, **k):  # noqa: ANN002, ANN003
        raise config.ModelNotFoundError("Cannot reach Ollama")

    monkeypatch.setattr(config, "detect_model", down)

    h = client.get("/health").json()
    assert h["status"] == "degraded" and h["model"] is None
    assert "Cannot reach Ollama" in h["model_error"]

    r = client.post("/chat", json={"chat_id": "c_down", "message": "hi"})
    assert r.status_code == 503
    assert "Cannot reach Ollama" in r.json()["detail"]
    # History still works with no model.
    assert client.get("/chats").status_code == 200


def test_health_recovers_when_ollama_returns(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        config, "detect_model",
        lambda *a, **k: (_ for _ in ()).throw(config.ModelNotFoundError("down")),
    )
    assert client.get("/health").json()["status"] == "degraded"
    monkeypatch.setattr(config, "detect_model", lambda *a, **k: "fake-vl:test")
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["model"] == "fake-vl:test"


def test_load_settings_tolerates_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(*a, **k):  # noqa: ANN002, ANN003
        raise config.ModelNotFoundError("down")

    monkeypatch.setattr(config, "detect_model", down)
    s = config.load_settings()
    assert s.model is None and s.model_error == "down"
    with pytest.raises(config.ModelNotFoundError):
        config.load_settings(require_model=True)


def test_aborted_stream_still_persists_turn(client: TestClient) -> None:
    """A client abort mid-answer keeps the turn in history, marked cancelled."""


    from glassview_ai.main import chat
    from glassview_ai.schemas import ChatRequest

    async def run() -> None:
        resp = await chat(ChatRequest(chat_id="c_abort", message="hi"))
        gen = resp.body_iterator
        assert await gen.__anext__() == b"Hello"
        await gen.aclose()  # what Starlette does when the client disconnects

    # Run on the app's own event-loop thread (sqlite handles are thread-bound).
    client.portal.call(run)
    msgs = client.get("/chats/c_abort").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Hello\n\n[cancelled]"


def test_bodyless_post_requires_json(client: TestClient) -> None:
    """A cross-site simple POST (no preflight) cannot clear a chat."""
    cid = client.post("/chats", json={}).json()["chat"]["id"]
    r = client.post(f"/chats/{cid}/clear", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    assert client.post(f"/chats/{cid}/clear", json={}).status_code == 200


# --- regression tests --------------------------------------------------------
def _png_b64() -> str:
    """A real (tiny) PNG, base64-encoded, as the capture path would send it."""
    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _send(client: TestClient, payload: dict) -> str:
    with client.stream("POST", "/chat", json=payload) as r:
        return "".join(r.iter_text())


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[list[dict]]:
    seen: list[list[dict]] = []

    async def capture(self, messages, *, temperature=0.2):  # noqa: ANN001
        seen.append(messages)
        yield "ok"

    monkeypatch.setattr(OllamaClient, "stream_chat", capture)
    return seen


def _recalled_chat_ids(client: TestClient, q: str) -> set[str]:
    hits = client.get("/recall", params={"q": q, "k": 10}).json()["hits"]
    return {h["meta"].get("chat_id") for h in hits}


def test_deleting_a_chat_forgets_its_memories(client: TestClient) -> None:
    _send(client, {"chat_id": "chat_del_mem", "message": "the router drops packets"})
    _send(client, {"chat_id": "chat_keep_mem", "message": "the router reboots at night"})
    assert "chat_del_mem" in _recalled_chat_ids(client, "router packets")

    assert client.delete("/chats/chat_del_mem").status_code == 200
    ids = _recalled_chat_ids(client, "router packets")
    assert "chat_del_mem" not in ids
    assert "chat_keep_mem" in ids


def test_clearing_a_chat_forgets_its_memories(client: TestClient) -> None:
    _send(client, {"chat_id": "chat_clear_mem", "message": "the router drops packets"})
    assert client.post("/chats/chat_clear_mem/clear", json={}).status_code == 200
    assert "chat_clear_mem" not in _recalled_chat_ids(client, "router packets")


def test_failed_turns_are_not_replayed_as_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self, messages, *, temperature=0.2):  # noqa: ANN001
        raise RuntimeError("model fell over")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(OllamaClient, "stream_chat", boom)
    _send(client, {"chat_id": "chat_hist_err", "message": "first try"})

    seen = _capture(monkeypatch)
    _send(client, {"chat_id": "chat_hist_err", "message": "second try"})

    sent = seen[-1]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert "[error]" not in str(sent)
    # The failed turn is still visible in the stored chat for the UI.
    stored = client.get("/chats/chat_hist_err").json()["messages"]
    assert any("[error]" in m["content"] for m in stored)


def test_model_history_drops_failed_pairs_and_fills_empty_questions() -> None:
    from glassview_ai.main import _model_history
    from glassview_ai.ollama_client import EMPTY_TURN_PROMPT

    rows = [
        {"role": "user", "content": "q1", "images": ["img"]},
        {"role": "assistant", "content": "a1", "images": []},
        {"role": "user", "content": "q2", "images": []},
        {"role": "assistant", "content": "[error] boom", "images": []},
        {"role": "user", "content": "q3", "images": []},
        {"role": "assistant", "content": "half\n\n[cancelled]", "images": []},
        {"role": "user", "content": "q4", "images": []},
        {"role": "assistant", "content": "[cancelled]", "images": []},
        {"role": "user", "content": "q5", "images": []},
        {"role": "assistant", "content": "(no response)", "images": []},
        {"role": "user", "content": "", "images": []},
        {"role": "assistant", "content": "a6", "images": []},
        {"role": "user", "content": "dangling", "images": []},
    ]
    assert _model_history(rows) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": EMPTY_TURN_PROMPT},
        {"role": "assistant", "content": "a6"},
    ]


def test_empty_message_turn_keeps_anthropic_alternation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A screenshot-only follow-up must not leave a gap in the replayed roles."""
    from glassview_ai.providers.anthropic_client import to_anthropic

    cid = "chat_empty_turn"
    _send(client, {"chat_id": cid, "message": "what is this", "image": _png_b64()})
    _send(client, {"chat_id": cid, "message": ""})  # reuses the last image

    seen = _capture(monkeypatch)
    _send(client, {"chat_id": cid, "message": "and now?"})
    _, msgs = to_anthropic(seen[-1])
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 2 + ["user"]


def test_images_are_sent_once_on_the_latest_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid = "chat_img_once"
    _send(client, {"chat_id": cid, "message": "what is this", "image": _png_b64()})

    seen = _capture(monkeypatch)
    _send(client, {"chat_id": cid, "message": "and the colour?"})
    counts = [len(m.get("images") or []) for m in seen[-1]]
    # system, replayed user, replayed assistant, current user (reused image).
    assert counts == [0, 0, 0, 1]


def test_undecodable_image_is_a_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    import glassview_ai.ocr.fuse as ocr_fuse

    monkeypatch.setattr(ocr_fuse, "tesseract_available", lambda: True)
    bad = base64.b64encode(b"notanimage").decode("ascii")
    r = client.post("/chat", json={"chat_id": "chat_bad_img", "message": "hi", "image": bad})
    assert r.status_code == 400
    assert "image" in r.json()["detail"].lower()


def test_ocr_extract_tolerates_undecodable_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    import glassview_ai.ocr.fuse as ocr_fuse

    monkeypatch.setattr(ocr_fuse, "tesseract_available", lambda: True)
    result = ocr_fuse.extract(b"notanimage")
    assert result.text == ""


@pytest.mark.parametrize("k", [-1, 0, 51])
def test_recall_rejects_out_of_range_k(client: TestClient, k: int) -> None:
    assert client.get("/recall", params={"q": "x", "k": k}).status_code == 422


def test_clearing_an_unknown_chat_is_a_404(client: TestClient) -> None:
    assert client.post("/chats/nope/clear", json={}).status_code == 404


def test_new_chat_title_is_stripped(client: TestClient) -> None:
    chat = client.post("/chats", json={"title": "  spaced  "}).json()["chat"]
    assert chat["title"] == "spaced"
    blank = client.post("/chats", json={"title": "   "}).json()["chat"]
    assert blank["title"] == "New chat"


@pytest.mark.parametrize(
    "reply",
    [
        '{"tool": "recall_memory", "args": ["printer"]}',
        '{"tool": "recall_memory", "args": "printer"}',
        '{"tool": 7, "args": {}}',
    ],
)
def test_agent_malformed_tool_call_is_not_a_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    replies = iter([reply, '{"final": "done"}'])

    async def scripted(self, messages, *, temperature=0.2):  # noqa: ANN001
        yield next(replies)

    monkeypatch.setattr(OllamaClient, "stream_chat", scripted)
    r = client.post("/agent", json={"question": "q"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "done"
    assert body["steps"][0]["observation"].startswith("error:")


@pytest.mark.parametrize(("final", "expected"), [("123", "123"), ('{"a": 1}', '{"a": 1}')])
def test_agent_non_string_final_is_not_a_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, final: str, expected: str
) -> None:
    async def scripted(self, messages, *, temperature=0.2):  # noqa: ANN001
        yield '{"final": ' + final + "}"

    monkeypatch.setattr(OllamaClient, "stream_chat", scripted)
    r = client.post("/agent", json={"question": "q"})
    assert r.status_code == 200
    assert r.json()["answer"] == expected


def test_blocking_work_runs_off_the_event_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OCR and the sync sqlite memory calls must not stall the event loop."""
    import threading

    import glassview_ai.main as main_mod
    from glassview_ai.ocr import OcrResult
    from glassview_ai.rag import MemoryStore

    threads: dict[str, int] = {}

    def fake_ocr(raw: bytes) -> OcrResult:
        threads["ocr"] = threading.get_ident()
        return OcrResult(text="", available=True)

    real_query, real_add = MemoryStore.query, MemoryStore.add

    def query(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
        threads["query"] = threading.get_ident()
        return real_query(self, *a, **k)

    def add(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
        threads["add"] = threading.get_ident()
        return real_add(self, *a, **k)

    async def stream(self, messages, *, temperature=0.2):  # noqa: ANN001
        threads["loop"] = threading.get_ident()
        yield "ok"

    monkeypatch.setattr(main_mod, "ocr_extract", fake_ocr)
    monkeypatch.setattr(MemoryStore, "query", query)
    monkeypatch.setattr(MemoryStore, "add", add)
    monkeypatch.setattr(OllamaClient, "stream_chat", stream)

    _send(client, {"chat_id": "chat_threads", "message": "hello there", "image": _png_b64()})
    assert {"ocr", "query", "add", "loop"} <= threads.keys()
    for name in ("ocr", "query", "add"):
        assert threads[name] != threads["loop"], name


def test_truncated_jpeg_is_a_400(client: TestClient) -> None:
    """verify() passes a cut-off JPEG; only a real decode catches it."""
    import base64
    import io
    import random

    from PIL import Image

    rng = random.Random(0)
    img = Image.new("RGB", (64, 64))
    img.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(64 * 64)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    half = buf.getvalue()[: len(buf.getvalue()) // 2]
    b64 = base64.b64encode(half).decode("ascii")
    r = client.post("/chat", json={"chat_id": "chat_trunc", "message": "hi", "image": b64})
    assert r.status_code == 400


def test_unreadable_stored_image_is_not_reused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy row holding a broken image must not be sent to the model."""
    import base64
    import functools

    from glassview_ai.main import app

    bad = base64.b64encode(b"notanimage").decode("ascii")
    client.portal.call(functools.partial(
        app.state.store.add_message, "chat_legacy", "user", "old", images=[bad]
    ))
    client.portal.call(app.state.store.add_message, "chat_legacy", "assistant", "old answer")

    seen = _capture(monkeypatch)
    _send(client, {"chat_id": "chat_legacy", "message": "again"})
    assert not any(m.get("images") for m in seen[-1])


@pytest.mark.parametrize("action", ["delete", "clear"])
def test_stream_finishing_after_delete_does_not_resurrect_the_chat(
    client: TestClient, action: str
) -> None:
    from glassview_ai import main as main_mod
    from glassview_ai.schemas import ChatRequest

    cid = f"chat_race_{action}"

    async def run() -> None:
        resp = await main_mod.chat(ChatRequest(chat_id=cid, message="router drops packets"))
        gen = resp.body_iterator
        assert await gen.__anext__() == b"Hello"
        if action == "delete":
            await main_mod.delete_chat(cid)
        else:
            await main_mod.clear_chat(cid)
        async for _ in gen:
            pass

    client.portal.call(run)
    assert cid not in _recalled_chat_ids(client, "router packets")
    if action == "delete":
        assert client.get(f"/chats/{cid}").status_code == 404
    else:
        assert client.get(f"/chats/{cid}").json()["messages"] == []
