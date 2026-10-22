"""GlassView AI orchestration service.

A local-first FastAPI service that fronts a local vision model (Ollama qwen3-vl)
and adds the applied-AI layer: OCR fusion, tool-use, RAG memory, and evals.

Every request carries its own chat id, so there is no global mutable session:
history is loaded from SQLite per request.
"""

__version__ = "0.2.0"
