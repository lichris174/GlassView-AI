"""sqlite-vec backed memory store with privacy-redacted text.

Memories are stored in two tables kept in lockstep by rowid: a ``vec0`` virtual
table holding the embedding and a plain table holding the (redacted) text and
metadata. Query embeds the request and returns the nearest memories by vector
distance.

The connection is shared across threads (the API runs these sync calls in a
worker thread so they do not block the event loop), so every DB call holds a
lock. Embedding runs outside the lock so slow embedders do not serialise
recall; the embedder must therefore be thread-safe (HashEmbedder is stateless).
"""

from __future__ import annotations

import json
import sqlite3
import struct
import threading
import time
from dataclasses import dataclass

import sqlite_vec

from ..privacy import redact
from .embed import Embedder, HashEmbedder


def _serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


@dataclass(frozen=True)
class MemoryHit:
    text: str
    distance: float
    meta: dict
    created_at: float


class MemoryStore:
    def __init__(self, path: str = ":memory:", embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashEmbedder()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self) -> None:
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories "
            f"USING vec0(embedding float[{self.embedder.dim}])"
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                rowid       INTEGER PRIMARY KEY,
                text        TEXT NOT NULL,
                meta        TEXT NOT NULL DEFAULT '{}',
                created_at  REAL NOT NULL
            )
            """
        )
        self.db.commit()

    def add(self, text: str, meta: dict | None = None, *, redact_text: bool = True) -> int:
        """Redact, embed, and store a memory. Returns its rowid.

        ``redact_text=False`` stores the text verbatim. That is a deliberate
        downgrade the user opts into (Settings -> Privacy redaction); it stays
        on by default so the guard is never lost by omission.
        """
        clean = redact(text)[0] if redact_text else text
        embedding = _serialize(self.embedder.embed(clean))
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO memories (text, meta, created_at) VALUES (?,?,?)",
                (clean, json.dumps(meta or {}), time.time()),
            )
            rowid = cur.lastrowid
            self.db.execute(
                "INSERT INTO vec_memories (rowid, embedding) VALUES (?,?)",
                (rowid, embedding),
            )
            self.db.commit()
        return int(rowid)

    def query(self, text: str, k: int = 5) -> list[MemoryHit]:
        embedding = _serialize(self.embedder.embed(text))
        with self._lock:
            rows = self.db.execute(
                """
                SELECT m.text, v.distance, m.meta, m.created_at
                FROM vec_memories v
                JOIN memories m ON m.rowid = v.rowid
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
                """,
                (embedding, k),
            ).fetchall()
        return [
            MemoryHit(text=r[0], distance=float(r[1]), meta=json.loads(r[2]), created_at=r[3])
            for r in rows
        ]

    def delete_by_chat(self, chat_id: str) -> int:
        """Forget every memory recorded from ``chat_id``. Returns how many.

        Called when a chat is deleted or cleared, so its turns stop surfacing in
        recall for other chats.
        """
        with self._lock:
            rowids = [
                r[0]
                for r in self.db.execute(
                    "SELECT rowid FROM memories "
                    "WHERE CAST(json_extract(meta, '$.chat_id') AS TEXT) = ?",
                    (chat_id,),
                )
            ]
            for rowid in rowids:
                self.db.execute("DELETE FROM vec_memories WHERE rowid = ?", (rowid,))
                self.db.execute("DELETE FROM memories WHERE rowid = ?", (rowid,))
            self.db.commit()
        return len(rowids)

    def close(self) -> None:
        with self._lock:
            self.db.close()
