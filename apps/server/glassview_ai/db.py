"""SQLite-backed chat store (async).

Replaces the prototype's ``past_chats.json`` + global module state. The service
is the single writer, and every operation is scoped by ``chat_id`` so concurrent
requests / windows cannot clobber a shared session.

Images are stored on the message row as a JSON array of base64 strings. (RAG
vectors land in a separate table in Phase 3 via sqlite-vec.)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import aiosqlite

MAX_TITLE_LENGTH = 42

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New chat',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    images      TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"chat_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def _title_from(text: str) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        return "New chat"
    return clean if len(clean) <= MAX_TITLE_LENGTH else clean[:MAX_TITLE_LENGTH] + "..."


class ChatStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("ChatStore not connected")
        return self._db

    # --- chats ---------------------------------------------------------------
    async def list_chats(self) -> list[dict]:
        rows = await self.db.execute_fetchall(
            """
            SELECT c.id, c.title, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS n
            FROM chats c ORDER BY c.updated_at DESC
            """
        )
        return [
            {"id": r["id"], "title": r["title"], "updated_at": r["updated_at"],
             "message_count": r["n"]}
            for r in rows
        ]

    async def create_chat(self, title: str | None = None, chat_id: str | None = None) -> dict:
        cid = chat_id or _new_id()
        now = _now()
        await self.db.execute(
            "INSERT OR IGNORE INTO chats (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (cid, (title or "New chat").strip() or "New chat", now, now),
        )
        await self.db.commit()
        return {"id": cid, "title": title or "New chat", "updated_at": now, "message_count": 0}

    async def get_chat(self, chat_id: str) -> dict | None:
        row = await (await self.db.execute(
            "SELECT id, title, created_at, updated_at FROM chats WHERE id = ?", (chat_id,)
        )).fetchone()
        if row is None:
            return None
        messages = await self.get_messages(chat_id)
        return {
            "id": row["id"], "title": row["title"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "messages": messages,
        }

    async def rename_chat(self, chat_id: str, title: str) -> bool:
        cur = await self.db.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), chat_id),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def delete_chat(self, chat_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def clear_messages(self, chat_id: str) -> None:
        await self.db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        await self.db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id)
        )
        await self.db.commit()

    # --- messages ------------------------------------------------------------
    async def get_messages(self, chat_id: str) -> list[dict]:
        rows = await self.db.execute_fetchall(
            "SELECT role, content, images FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        )
        return [
            {"role": r["role"], "content": r["content"], "images": json.loads(r["images"])}
            for r in rows
        ]

    async def last_image(self, chat_id: str) -> str | None:
        rows = await self.db.execute_fetchall(
            "SELECT images FROM messages WHERE chat_id = ? AND images != '[]' "
            "ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )
        for r in rows:
            imgs = json.loads(r["images"])
            if imgs:
                return imgs[0]
        return None

    async def add_message(
        self, chat_id: str, role: str, content: str, images: list[str] | None = None
    ) -> None:
        await self.db.execute("INSERT OR IGNORE INTO chats (id, title, created_at, updated_at) "
                              "VALUES (?,?,?,?)", (chat_id, "New chat", _now(), _now()))
        await self.db.execute(
            "INSERT INTO messages (chat_id, role, content, images, created_at) "
            "VALUES (?,?,?,?,?)",
            (chat_id, role, content, json.dumps(images or []), _now()),
        )
        # Auto-title from first user message if still default.
        if role == "user" and content.strip():
            row = await (await self.db.execute(
                "SELECT title FROM chats WHERE id = ?", (chat_id,)
            )).fetchone()
            if row is not None and (not row["title"] or row["title"] == "New chat"):
                await self.db.execute(
                    "UPDATE chats SET title = ? WHERE id = ?",
                    (_title_from(content), chat_id),
                )
        await self.db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?", (_now(), chat_id)
        )
        await self.db.commit()
