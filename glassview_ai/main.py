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
from .agents import run_agent
from .agents.tools import build_registry
from .db import ChatStore
from .ocr import extract as ocr_extract
from .ocr import fuse_prompt
from .ollama_client import OllamaClient, build_messages
from .providers import PROVIDERS, MissingApiKeyError, build_client
from .rag import HashEmbedder, MemoryStore, fuse_recall, select_hits
from .routing import RoutePolicy, route
from .schemas import (
    AgentRequest,
    AgentResponse,
    AgentStepOut,
    ChatRequest,
    ChatSummary,
    HealthResponse,
    NewChatRequest,
    RenameRequest,
)

# How many raw memory hits to pull before filtering; select_hits trims to the few
# that clear the distance cut and are not from the current chat.
RECALL_CANDIDATES = 10

# Resolved at startup in the lifespan; kept on app.state for testability.


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = config.load_settings()
    store = ChatStore(settings.db_path)
    await store.connect()
    app.state.settings = settings
    app.state.store = store
    app.state.ollama = OllamaClient(settings.ollama_host, settings.model)
    # Routing has one installed model today, so fast and strong are the same tag;
    # the recorded reason still shows when an escalation would have happened.
    app.state.policy = RoutePolicy(fast=settings.model, strong=settings.model)
    # Memory lives beside the chat DB and uses the offline embedder by default
    # so recall works without a running embedding model.
    app.state.memory = MemoryStore(
        path=f"{settings.db_path}.memories.db", embedder=HashEmbedder()
    )
    # Tools the agent loop may call. Read-only and local; see agents/tools.py.
    app.state.tools = build_registry(app.state.memory, store)
    try:
        yield
    finally:
        await store.close()
        app.state.memory.close()


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
    return HealthResponse(
        status="ok", model=s.model, ollama_host=s.ollama_host, providers=list(PROVIDERS)
    )


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
def _image_bytes(image: str) -> bytes | None:
    """Decode a data URL or bare base64 image to raw bytes, or None on failure."""
    import base64

    try:
        b64 = image.split(",", 1)[1] if "," in image else image
        return base64.b64decode(b64)
    except Exception:  # noqa: BLE001 - a bad image just disables OCR for this turn
        return None


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    store = _store(app)
    memory: MemoryStore = app.state.memory

    await store.create_chat(chat_id=req.chat_id)  # idempotent
    history = (await store.get_messages(req.chat_id))[-config.MAX_HISTORY_TURNS * 2:]

    # A new image resets the visual context for this chat; otherwise reuse last.
    image = req.image or await store.last_image(req.chat_id)

    # OCR fusion: fold any on-screen text into the prompt (no-op without Tesseract
    # or without an image). The stored user message stays the original question.
    prompt = req.message
    if image:
        raw = _image_bytes(image)
        if raw is not None:
            ocr = ocr_extract(raw)
            prompt = fuse_prompt(req.message, ocr.text)

    # Recall fusion: fold in relevant notes from *other* chats. This chat's own
    # turns are already replayed as history, so they are excluded to avoid both
    # wasted context and the model parroting its previous answer back.
    if req.recall and req.message.strip():
        hits = select_hits(
            memory.query(req.message, k=RECALL_CANDIDATES),
            req.message,
            exclude_chat_id=req.chat_id,
        )
        prompt = fuse_recall(prompt, hits)

    # Route to a model tier based on the prompt and whether an image is present.
    # Routing only governs the local path: a cloud provider is a single model the
    # user chose explicitly, so there is no tier to escalate to.
    decision = route(req.message, has_image=bool(image), policy=app.state.policy)
    settings = app.state.settings

    if req.provider in ("openai", "anthropic", "deepseek") or req.api_key:
        try:
            client = build_client(
                req.provider,
                api_key=req.api_key,
                model=req.model,
                ollama_host=settings.ollama_host,
                ollama_model=settings.model,
            )
        except MissingApiKeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ImportError as exc:  # provider SDK not installed
            raise HTTPException(
                status_code=501,
                detail=f"Provider unavailable: {exc}",
            ) from exc
        chosen_model = client.model
    else:
        # Reuse the lifespan client when routing lands on the default model;
        # only spin up a different client if routing ever picks another tag.
        client = (
            app.state.ollama
            if decision.model == settings.model
            else OllamaClient(settings.ollama_host, decision.model)
        )
        chosen_model = decision.model

    messages = build_messages(config.SYSTEM_PROMPT, history, prompt, image)

    async def event_stream() -> AsyncIterator[bytes]:
        answer_parts: list[str] = []
        error: str | None = None
        try:
            async for chunk in client.stream_chat(messages):
                answer_parts.append(chunk)
                yield chunk.encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            # The 200 header is already sent, so a raised error would otherwise
            # reach the client as a silent empty body. Surface it in the stream
            # instead, and record it so the failed turn is not lost.
            error = f"[error] {exc}"
            yield error.encode("utf-8")
        finally:
            # If an error occurred mid-stream, record the error rather than the
            # partial tokens so the chat history matches what the user saw.
            answer = error if error is not None else ("".join(answer_parts) or "(no response)")
            # Persist the turn (store the image only on the message that introduced it).
            await store.add_message(
                req.chat_id, "user", req.message or "",
                images=[req.image] if req.image else [],
            )
            await store.add_message(req.chat_id, "assistant", answer)
            # Remember successful turns for later recall; redaction happens inside
            # the store. Failed turns are not worth recalling.
            if error is None and answer_parts:
                memory.add(
                    f"Q: {req.message}\nA: {answer}",
                    meta={"chat_id": req.chat_id, "model": chosen_model},
                    redact_text=req.redact,
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- agent (bounded tool use) ------------------------------------------------
@app.post("/agent", response_model=AgentResponse)
async def agent(req: AgentRequest) -> AgentResponse:
    """Answer a question through the bounded tool-use loop.

    Deliberately separate from ``/chat``: the loop is multi-turn and blocking
    (it cannot stream a token at a time), and an ordinary chat turn should not
    pay for tool round-trips it does not need.
    """
    registry = app.state.tools
    ollama: OllamaClient = app.state.ollama

    async def complete(transcript: list[dict[str, str]]) -> str:
        return "".join([chunk async for chunk in ollama.stream_chat(transcript)])

    try:
        result = await run_agent(
            req.question,
            complete,
            registry,
            system_prompt=config.SYSTEM_PROMPT,
            max_steps=req.max_steps,
        )
    except Exception as exc:  # noqa: BLE001 - upstream model failure, not a bug here
        # /chat surfaces model failures inline in its stream; this path has no
        # stream to write into, so report it as a bad gateway with the reason
        # (model not pulled, out of memory, daemon down) instead of a 500.
        raise HTTPException(status_code=502, detail=f"Model call failed: {exc}") from exc
    return AgentResponse(
        answer=result.answer,
        steps=[
            AgentStepOut(tool=st.tool, args=st.args, observation=st.observation)
            for st in result.steps
        ],
        stopped_reason=result.stopped_reason,
        tools=registry.names(),
    )


# --- memory recall -----------------------------------------------------------
@app.get("/recall")
async def recall(q: str, k: int = 5) -> dict:
    """Semantic search over remembered turns ("what was that error yesterday")."""
    memory: MemoryStore = app.state.memory
    hits = memory.query(q, k=k)
    return {
        "hits": [
            {"text": h.text, "distance": h.distance, "meta": h.meta,
             "created_at": h.created_at}
            for h in hits
        ]
    }
