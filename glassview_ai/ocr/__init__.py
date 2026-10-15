"""OCR fusion: extract on-screen text and fold it into the prompt so the model
reads exact strings (error codes, paths, tokens) instead of guessing them from
pixels. The Tesseract backend is optional; when it is absent, extraction
returns empty and the chat path simply proceeds image-only."""

from .fuse import OcrResult, extract, fuse_prompt, tesseract_available

__all__ = ["OcrResult", "extract", "fuse_prompt", "tesseract_available"]
