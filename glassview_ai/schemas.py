"""Pydantic request/response models shared with the TS frontend via OpenAPI."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatSummary(BaseModel):
    id: str
    title: str
    updated_at: str | None = None
    message_count: int = 0


class NewChatRequest(BaseModel):
    title: str | None = None


class RenameRequest(BaseModel):
    title: str


class ChatRequest(BaseModel):
    """A single turn. ``chat_id`` scopes server state per-request (no globals)."""

    chat_id: str
    message: str = ""
    # Accept either a fresh image (data URL or base64) or omit to reuse the
    # chat's last image. The server resolves which image applies.
    image: str | None = None
    # Redact secrets/PII before this turn is written to memory. Defaults on, so
    # a client that never sends the field keeps the guard.
    redact: bool = True
    # Fold relevant memories from *other* chats into the prompt.
    recall: bool = True
    # Cloud dispatch. Omit for local Ollama. The key is used for this call only
    # and is never persisted, logged, or written to memory.
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None


class AgentStepOut(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    observation: str


class AgentRequest(BaseModel):
    """One question answered through the bounded tool-use loop."""

    question: str
    max_steps: int = Field(default=4, ge=1, le=8)


class AgentResponse(BaseModel):
    answer: str
    steps: list[AgentStepOut] = Field(default_factory=list)
    stopped_reason: str = "final"
    tools: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str  # "ok", or "degraded" when no local model is available
    model: str | None
    model_error: str | None = None
    ollama_host: str
    providers: list[str] = Field(default_factory=list)
