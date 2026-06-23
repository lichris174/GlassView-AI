"""FastAPI app: streaming chat + SQLite history. No global session state.

Each request carries a ``chat_id``; history is loaded from SQLite per-request,
so multiple windows / concurrent requests stay isolated (the prototype kept one
module-level conversation for the whole process).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import config
from .db import ChatStore
from .ollama_client import OllamaClient, build_messages
from .schemas import (
    ChatRequest,
    ChatSummary,
    HealthResponse,
    NewChatRequest,
    RenameRequest,
)

# Resolved at startup in the lifespan; kept on app.state for testability.


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = config.load_settings()
    store = ChatStore(settings.db_path)
    await store.connect()
    app.state.settings = settings
    app.state.store = store
    app.state.ollama = OllamaClient(settings.ollama_host, settings.model)
    try:
        yield
    finally:
        await store.close()


app = FastAPI(title="GlassView AI", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only desktop app; tightened behind Tauri in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


def _store(app: FastAPI) -> ChatStore:
    return app.state.store


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = app.state.settings
    return HealthResponse(status="ok", model=s.model, ollama_host=s.ollama_host)


# --- chat CRUD ---------------------------------------------------------------
@app.get("/chats")
async def list_chats() -> dict:
    return {"chats": [ChatSummary(**c).model_dump() for c in await _store(app).list_chats()]}


@app.post("/chats")
async def new_chat(req: NewChatRequest) -> dict:
    chat = await _store(app).create_chat(title=req.title)
    return {"chat": ChatSummary(**chat).model_dump()}


@app.get("/chats/{chat_id}")
async def get_chat(chat_id: str) -> dict:
    chat = await _store(app).get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.patch("/chats/{chat_id}")
async def rename_chat(chat_id: str, req: RenameRequest) -> dict:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Missing title")
    if not await _store(app).rename_chat(chat_id, title):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True}


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str) -> dict:
    if not await _store(app).delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True}


@app.post("/chats/{chat_id}/clear")
async def clear_chat(chat_id: str) -> dict:
    await _store(app).clear_messages(chat_id)
    return {"ok": True}


# --- streaming chat ----------------------------------------------------------
@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    store = _store(app)
    ollama: OllamaClient = app.state.ollama

    await store.create_chat(chat_id=req.chat_id)  # idempotent
    history = (await store.get_messages(req.chat_id))[-config.MAX_HISTORY_TURNS * 2:]

    # A new image resets the visual context for this chat; otherwise reuse last.
    image = req.image or await store.last_image(req.chat_id)
    messages = build_messages(config.SYSTEM_PROMPT, history, req.message, image)

    async def event_stream() -> AsyncIterator[bytes]:
        answer_parts: list[str] = []
        error: str | None = None
        try:
            async for chunk in ollama.stream_chat(messages):
                answer_parts.append(chunk)
                yield chunk.encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            # The 200 header is already sent, so a raised error would otherwise
            # reach the client as a silent empty body. Surface it in the stream
            # instead, and record it so the failed turn is not lost.
            error = f"[error] {exc}"
            yield error.encode("utf-8")
        finally:
            answer = "".join(answer_parts) or error or "(no response)"
            # Persist the turn (store the image only on the message that introduced it).
            await store.add_message(
                req.chat_id, "user", req.message or "",
                images=[req.image] if req.image else [],
            )
            await store.add_message(req.chat_id, "assistant", answer)

    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
