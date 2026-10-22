"""FastAPI app: streaming chat + SQLite history. No global session state.

Each request carries a ``chat_id``; history is loaded from SQLite per-request,
so multiple windows / concurrent requests stay isolated (the prototype kept one
module-level conversation for the whole process).
"""

from __future__ import annotations

import asyncio
import collections
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse

from . import config
from .agents import run_agent
from .agents.tools import build_registry
from .db import ChatStore
from .ocr import extract as ocr_extract
from .ocr import fuse_prompt
from .ollama_client import EMPTY_TURN_PROMPT, OllamaClient, build_messages
from .providers import PROVIDERS, MissingApiKeyError, build_client, detect_provider
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

# How a turn that did not complete is stored. The UI shows these as-is, but they
# are not real answers, so _model_history never replays them to the model.
# Recognising them by text is a stopgap: a status column on messages would be
# exact, but needs a schema migration the store does not have yet.
ERROR_PREFIX = "[error] "
CANCELLED_MARK = "[cancelled]"
NO_RESPONSE = "(no response)"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = config.load_settings()
    store = ChatStore(settings.db_path)
    await store.connect()
    app.state.settings = settings
    app.state.store = store
    # The local model may be missing at startup (Ollama not running). That is not
    # fatal: cloud providers and history still work, and _local_model() retries.
    app.state.local_model = settings.model
    app.state.model_error = settings.model_error
    # Memory lives beside the chat DB and uses the offline embedder by default
    # so recall works without a running embedding model.
    app.state.memory = MemoryStore(
        path=f"{settings.db_path}.memories.db", embedder=HashEmbedder()
    )
    # Tools the agent loop may call. Read-only and local; see agents/tools.py.
    app.state.tools = build_registry(app.state.memory, store)
    # Bumped whenever a chat is deleted or cleared, so a /chat stream that was
    # already running can tell its turn no longer belongs in that chat.
    app.state.chat_epochs = collections.Counter()
    try:
        yield
    finally:
        await store.close()
        app.state.memory.close()


app = FastAPI(title="GlassView AI", version="0.2.0", lifespan=lifespan)
# Only the desktop UI may call this API from a browser context. A wildcard here
# would let any website the user visits read and delete their chats.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.allowed_origins()),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
# Reject requests whose Host is not loopback. This blocks DNS rebinding, where a
# hostile domain re-resolves to 127.0.0.1 and becomes "same-origin" with us.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts()))


def _store(app: FastAPI) -> ChatStore:
    return app.state.store


async def _detect_local_model() -> str | None:
    """Ask Ollama for a usable vision model and record the result on app.state.

    Runs the blocking HTTP probe in a thread so a slow daemon cannot stall the
    event loop (and every other request) for the probe's timeout.
    """
    host = app.state.settings.ollama_host
    try:
        model = await asyncio.to_thread(config.detect_model, host)
    except config.ModelNotFoundError as exc:
        app.state.local_model, app.state.model_error = None, str(exc)
        return None
    app.state.local_model, app.state.model_error = model, None
    return model


async def _local_model() -> str:
    """The local model for this request, re-detecting if it was missing.

    Raises 503 with Ollama's reason so the UI can tell the user what to fix.
    """
    model = app.state.local_model or await _detect_local_model()
    if model is None:
        raise HTTPException(status_code=503, detail=app.state.model_error)
    return model


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Probe on every call so the UI notices Ollama starting or stopping without a
    # backend restart. The frontend polls this every 10-30 s, so the cost is small.
    model = await _detect_local_model()
    return HealthResponse(
        status="ok" if model else "degraded",
        model=model,
        model_error=app.state.model_error,
        ollama_host=app.state.settings.ollama_host,
        providers=list(PROVIDERS),
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


async def _forget_chat(chat_id: str) -> None:
    """Drop a chat's memories so its turns stop surfacing in recall elsewhere."""
    memory: MemoryStore = app.state.memory
    app.state.chat_epochs[chat_id] += 1
    await asyncio.to_thread(memory.delete_by_chat, chat_id)


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str) -> dict:
    if not await _store(app).delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    await _forget_chat(chat_id)
    return {"ok": True}


def require_json(request: Request) -> None:
    """Reject bodyless POSTs that are not JSON.

    A cross-site page can send a "simple" POST (no CORS preflight) as long as it
    is not JSON. Routes with a JSON body are already safe because FastAPI rejects
    other content types; this covers routes that take no body.
    """
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(status_code=415, detail="Expected application/json")


@app.post("/chats/{chat_id}/clear", dependencies=[Depends(require_json)])
async def clear_chat(chat_id: str) -> dict:
    if not await _store(app).clear_messages(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    await _forget_chat(chat_id)
    return {"ok": True}


# --- streaming chat ----------------------------------------------------------
def _image_bytes(image: str) -> bytes | None:
    """Decode a data URL or bare base64 image to raw bytes, or None when it is
    not base64 or not an image Pillow can fully decode.

    ``load()`` rather than ``verify()``: verify only checks headers and passes a
    truncated JPEG that would then fail at the model or in OCR.
    """
    import base64
    import io

    from PIL import Image

    try:
        b64 = image.split(",", 1)[1] if "," in image else image
        raw = base64.b64decode(b64)
        Image.open(io.BytesIO(raw)).load()
    except Exception:  # noqa: BLE001 - any decode failure means "not an image"
        return None
    return raw


def _failed_answer(answer: str) -> bool:
    return (
        answer.startswith(ERROR_PREFIX)
        or answer.endswith(CANCELLED_MARK)
        or answer == NO_RESPONSE
    )


def _model_history(rows: list[dict]) -> list[dict]:
    """Turn stored rows into the history replayed to the model.

    Only complete user/assistant pairs are kept, so roles strictly alternate
    (Anthropic needs that). A pair whose answer failed, was cancelled, or was
    empty is dropped: the UI still shows it, but the model should not learn from
    it. An empty question is replayed as what the model was actually asked.
    Images are stripped: the current turn carries the one image that applies,
    so history never resends screenshots.
    """
    turns: list[dict] = []
    i = 0
    while i < len(rows) - 1:
        question, answer = rows[i], rows[i + 1]
        if question["role"] != "user" or answer["role"] != "assistant":
            i += 1
            continue
        if not _failed_answer(answer["content"]):
            turns.append({
                "role": "user",
                "content": (question["content"] or "").strip() or EMPTY_TURN_PROMPT,
            })
            turns.append({"role": "assistant", "content": answer["content"]})
        i += 2
    return turns[-config.MAX_HISTORY_TURNS * 2:]


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    store = _store(app)
    memory: MemoryStore = app.state.memory

    # Reject an unreadable new image up front, while an HTTP error can still be
    # returned; once streaming starts the status is already 200. Decoding runs
    # in a thread because a full screenshot is a few MB.
    raw = await asyncio.to_thread(_image_bytes, req.image) if req.image else None
    if req.image and raw is None:
        raise HTTPException(status_code=400, detail="Image could not be decoded")

    await store.create_chat(chat_id=req.chat_id)  # idempotent
    epoch = app.state.chat_epochs[req.chat_id]
    history = _model_history(await store.get_messages(req.chat_id))

    # A new image resets the visual context for this chat; otherwise reuse last.
    image = req.image or await store.last_image(req.chat_id)
    if image and raw is None:
        raw = await asyncio.to_thread(_image_bytes, image)
        if raw is None:
            # A stored image from before decoding was checked; never send it.
            image = None

    # OCR fusion: fold any on-screen text into the prompt (no-op without Tesseract
    # or without an image). The stored user message stays the original question.
    # Tesseract is a blocking subprocess, so it runs off the event loop.
    prompt = req.message
    if raw is not None:
        ocr = await asyncio.to_thread(ocr_extract, raw)
        prompt = fuse_prompt(req.message, ocr.text)

    # Recall fusion: fold in relevant notes from *other* chats. This chat's own
    # turns are already replayed as history, so they are excluded to avoid both
    # wasted context and the model parroting its previous answer back.
    if req.recall and req.message.strip():
        hits = select_hits(
            await asyncio.to_thread(memory.query, req.message, k=RECALL_CANDIDATES),
            req.message,
            exclude_chat_id=req.chat_id,
        )
        prompt = fuse_recall(prompt, hits)

    settings = app.state.settings
    provider = req.provider if req.provider in PROVIDERS else detect_provider(req.api_key)

    if provider != "ollama":
        try:
            client = build_client(
                provider,
                api_key=req.api_key,
                model=req.model,
                ollama_host=settings.ollama_host,
                ollama_model=app.state.local_model or "",
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
        # Route to a model tier based on the prompt and whether an image is
        # present. Only one local model is installed today, so fast and strong
        # are the same tag; the decision's reason still records when an
        # escalation would have happened. Cloud providers skip routing: the
        # user picked that one model explicitly.
        local = await _local_model()
        policy = RoutePolicy(fast=local, strong=local)
        decision = route(req.message, has_image=bool(image), policy=policy)
        client = OllamaClient(settings.ollama_host, decision.model)
        chosen_model = decision.model

    messages = build_messages(config.SYSTEM_PROMPT, history, prompt, image)

    async def persist(answer: str, remember: bool) -> None:
        # The chat may have been deleted or cleared while this answer streamed.
        # Writing anyway would recreate it (add_message upserts the chat) or
        # refill it, and re-add a memory the user just asked to forget.
        if app.state.chat_epochs[req.chat_id] != epoch:
            return
        # Store the image only on the message that introduced it.
        await store.add_message(
            req.chat_id, "user", req.message or "",
            images=[req.image] if req.image else [],
        )
        await store.add_message(req.chat_id, "assistant", answer)
        # Remember successful turns for later recall; redaction happens inside
        # the store. Failed or cancelled turns are not worth recalling.
        if remember and app.state.chat_epochs[req.chat_id] == epoch:
            await asyncio.to_thread(
                memory.add,
                f"Q: {req.message}\nA: {answer}",
                meta={"chat_id": req.chat_id, "model": chosen_model},
                redact_text=req.redact,
            )

    async def event_stream() -> AsyncIterator[bytes]:
        answer_parts: list[str] = []
        error: str | None = None
        cancelled = False
        try:
            async for chunk in client.stream_chat(messages):
                answer_parts.append(chunk)
                yield chunk.encode("utf-8")
        except (asyncio.CancelledError, GeneratorExit):
            # The client aborted (user switched chats or hit cancel). Depending
            # on where the disconnect lands, Starlette either cancels the task or
            # closes this generator.
            cancelled = True
            raise
        except Exception as exc:  # noqa: BLE001
            # The 200 header is already sent, so a raised error would otherwise
            # reach the client as a silent empty body. Surface it in the stream
            # instead, and record it so the failed turn is not lost.
            error = f"{ERROR_PREFIX}{exc}"
            yield error.encode("utf-8")
        finally:
            partial = "".join(answer_parts)
            if error is not None:
                # Record the error rather than partial tokens so history matches
                # what the user saw.
                answer = error
            elif cancelled:
                answer = f"{partial}\n\n{CANCELLED_MARK}" if partial else CANCELLED_MARK
            else:
                answer = partial or NO_RESPONSE
            ok = error is None and not cancelled and bool(answer_parts)
            # Shielded: on a client abort this task is being cancelled, and an
            # unshielded await here would drop the turn from history.
            await asyncio.shield(persist(answer, remember=ok))

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
    ollama = OllamaClient(app.state.settings.ollama_host, await _local_model())

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
async def recall(q: str, k: int = Query(5, ge=1, le=50)) -> dict:
    """Semantic search over remembered turns ("what was that error yesterday")."""
    memory: MemoryStore = app.state.memory
    hits = await asyncio.to_thread(memory.query, q, k=k)
    return {
        "hits": [
            {"text": h.text, "distance": h.distance, "meta": h.meta,
             "created_at": h.created_at}
            for h in hits
        ]
    }
