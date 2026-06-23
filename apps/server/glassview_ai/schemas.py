"""Pydantic request/response models shared with the TS frontend via OpenAPI."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatSummary(BaseModel):
    id: str
    title: str
    updated_at: str | None = None
    message_count: int = 0


class Message(BaseModel):
    role: str
    content: str
    # base64 image payloads (data URL or bare base64); empty for text-only turns
    images: list[str] = Field(default_factory=list)


class ChatDetail(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    updated_at: str | None = None
    messages: list[Message] = Field(default_factory=list)


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


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_host: str
