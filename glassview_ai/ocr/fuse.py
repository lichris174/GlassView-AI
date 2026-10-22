"""Tesseract-backed OCR with graceful absence, plus prompt fusion.

``extract`` returns text and a confidence flag; if Tesseract is not installed it
returns an empty result rather than raising, so OCR is a pure enhancement.
``fuse_prompt`` merges extracted text into the user's question.
"""

from __future__ import annotations

import functools
import io
from dataclasses import dataclass

_MAX_OCR_CHARS = 4000  # keep the fused prompt bounded


@dataclass(frozen=True)
class OcrResult:
    text: str
    available: bool


@functools.lru_cache(maxsize=1)
def tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - any failure means OCR is unavailable
        return False


def extract(image: bytes) -> OcrResult:
    """Run OCR over PNG/JPEG bytes; empty if Tesseract is unavailable or the
    bytes are not a readable image."""
    if not tesseract_available():
        return OcrResult(text="", available=False)
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(image))
        text = pytesseract.image_to_string(img).strip()
    except Exception:  # noqa: BLE001 - unreadable image: skip OCR, do not fail the turn
        return OcrResult(text="", available=True)
    return OcrResult(text=text[:_MAX_OCR_CHARS], available=True)


def fuse_prompt(question: str, ocr_text: str) -> str:
    """Prepend extracted screen text to the question, if any was found."""
    ocr_text = (ocr_text or "").strip()
    if not ocr_text:
        return question
    return (
        "Screen text extracted via OCR (may contain errors):\n"
        f"\"\"\"\n{ocr_text[:_MAX_OCR_CHARS]}\n\"\"\"\n\n"
        f"{question}"
    )
