from __future__ import annotations

from glassview_ai.ocr import extract, fuse_prompt, tesseract_available


def test_fuse_prepends_ocr_text() -> None:
    fused = fuse_prompt("What is the error?", "Error: ECONNREFUSED 127.0.0.1:5432")
    assert "ECONNREFUSED" in fused
    assert fused.endswith("What is the error?")


def test_fuse_noop_when_no_text() -> None:
    assert fuse_prompt("just answer", "") == "just answer"
    assert fuse_prompt("just answer", "   ") == "just answer"


def test_extract_is_graceful_without_tesseract() -> None:
    # Tiny non-image byte string: with no Tesseract this returns empty rather
    # than raising; with Tesseract present it would also not crash the suite.
    if tesseract_available():
        return
    result = extract(b"not really an image")
    assert result.text == "" and result.available is False
