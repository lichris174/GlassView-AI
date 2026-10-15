"""sqlite-vec backed memory store with privacy-redacted text.

Memories are stored in two tables kept in lockstep by rowid: a ``vec0`` virtual
table holding the embedding and a plain table holding the (redacted) text and
metadata. Query embeds the request and returns the nearest memories by vector
distance.
"""

from __future__ import annotations

import json
import sqlite3
import struct
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
        self.db = sqlite3.connect(path)
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
        cur = self.db.execute(
            "INSERT INTO memories (text, meta, created_at) VALUES (?,?,?)",
            (clean, json.dumps(meta or {}), time.time()),
        )
        rowid = cur.lastrowid
        self.db.execute(
            "INSERT INTO vec_memories (rowid, embedding) VALUES (?,?)",
            (rowid, _serialize(self.embedder.embed(clean))),
        )
        self.db.commit()
        return int(rowid)

    def query(self, text: str, k: int = 5) -> list[MemoryHit]:
        rows = self.db.execute(
            """
            SELECT m.text, v.distance, m.meta, m.created_at
            FROM vec_memories v
            JOIN memories m ON m.rowid = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (_serialize(self.embedder.embed(text)), k),
        ).fetchall()
        return [
            MemoryHit(text=r[0], distance=float(r[1]), meta=json.loads(r[2]), created_at=r[3])
            for r in rows
        ]

    def close(self) -> None:
        self.db.close()
