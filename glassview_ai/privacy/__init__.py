"""Local-only privacy guard: strip secrets and PII from text before it is
persisted (notably into the RAG memory store) or logged. Detection is pattern
based and runs entirely on-device; nothing leaves the machine."""

from .redact import Finding, redact, scan

__all__ = ["Finding", "redact", "scan"]
