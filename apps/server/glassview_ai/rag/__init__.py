"""Capture/answer memory with semantic recall over sqlite-vec.

Text is redacted (see ``privacy``) before it is embedded and stored, so the
memory never holds raw secrets. Embedding is pluggable: a deterministic local
hashing embedder keeps recall working fully offline (and makes tests
reproducible), while an Ollama-backed embedder can be swapped in for quality.
"""

from .embed import Embedder, HashEmbedder, OllamaEmbedder
from .store import MemoryHit, MemoryStore

__all__ = ["Embedder", "HashEmbedder", "OllamaEmbedder", "MemoryHit", "MemoryStore"]
