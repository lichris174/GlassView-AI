"""GlassView AI orchestration service.

A local-first FastAPI service that fronts a local vision model (Ollama qwen3-vl)
and adds the applied-AI layer: OCR fusion, tool-use, RAG memory, and evals.

Phase 1 scope (this module set): clean streaming chat + SQLite-backed history,
with no global mutable session (every request carries its own chat id).
"""

__version__ = "0.2.0"
