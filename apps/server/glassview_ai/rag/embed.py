"""Embedders. The hashing embedder is dependency-free and deterministic; the
Ollama embedder calls a local model for higher-quality vectors."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class HashEmbedder:
    """Hashing-trick bag-of-words embedding.

    Each token is hashed into a bucket with a signed weight; the result is L2
    normalized so cosine/L2 distance reflects lexical overlap. Not semantic, but
    deterministic and offline, which is what tests and a no-network fallback
    need.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        return _l2_normalize(vec)


class OllamaEmbedder:
    """Embeddings from a local Ollama model via /api/embeddings."""

    def __init__(self, host: str, model: str = "nomic-embed-text", dim: int = 768) -> None:
        self.host = host
        self.model = model
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        import httpx

        resp = httpx.post(
            f"{self.host}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        vec = resp.json()["embedding"]
        self.dim = len(vec)
        return _l2_normalize(vec)
