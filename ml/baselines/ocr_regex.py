"""Baseline: what GlassView does today, turned into boxes.

Tesseract reads every word with its position; the app's own redaction rules
(glassview_ai/privacy/redact.py) run over each line of text; the words a match
touches become a box. This is the strongest *rule-based* system available
without training, and the one the detector has to beat to justify itself.

Known blind spots, by design of the approach rather than of this code: it can
only find text (no faces or ID photos), it misses what OCR misreads, and the
rules have no notion of "private message", so that class is never detected.
Needs the Tesseract binary (``winget install UB-Mannheim.TesseractOCR``).
"""

from __future__ import annotations

from collections import defaultdict

from PIL import Image

from glassview_ai.privacy.redact import find_spans

from ..labels import Box

# Redaction rule kinds mapped onto the detector's classes.
KIND_TO_CLASS = {
    "PRIVATE_KEY": "api_key",
    "JWT": "api_key",
    "AWS_ACCESS_KEY": "api_key",
    "GITHUB_TOKEN": "api_key",
    "SLACK_TOKEN": "api_key",
    "SECRET": "api_key",
    "CREDIT_CARD": "financial",
    "EMAIL": "personal_id",
    "SSN": "personal_id",
    "PHONE": "personal_id",
}


def boxes_from_ocr(data: dict[str, list]) -> list[Box]:
    """Turn pytesseract ``image_to_data`` output into boxes around matches.

    Words are grouped into lines, joined with single spaces while recording
    each word's character span, so a regex match over the line text can be
    mapped back to the words (and pixels) it covers.
    """
    lines: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for i, word in enumerate(data["text"]):
        if str(word).strip():
            lines[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(i)

    boxes: list[Box] = []
    seen: set[tuple[float, float, float, float]] = set()
    for idxs in lines.values():
        idxs.sort(key=lambda i: data["word_num"][i])
        text, spans = "", []
        for i in idxs:
            start = len(text) + (1 if text else 0)
            text = f"{text} {data['text'][i]}" if text else str(data["text"][i])
            spans.append((i, start, len(text)))
        for kind, m_start, m_end in find_spans(text):
            hit = [i for i, s, e in spans if s < m_end and e > m_start]
            if not hit:
                continue
            coords = (
                min(data["left"][i] for i in hit),
                min(data["top"][i] for i in hit),
                max(data["left"][i] + data["width"][i] for i in hit),
                max(data["top"][i] + data["height"][i] for i in hit),
            )
            # Several rules can match the same words ("token: ghp_..." hits both
            # GITHUB_TOKEN and SECRET). Rules run most-specific first, so keep
            # the first; a duplicate box would count as a false positive in AP.
            if coords in seen:
                continue
            seen.add(coords)
            boxes.append(Box(KIND_TO_CLASS.get(kind, "api_key"), *coords))
    return boxes


class OcrRegex:
    name = "ocr_regex"

    def __init__(self) -> None:
        import pytesseract

        self._tess = pytesseract
        # Recorded in the manifest: OCR version changes what the baseline sees.
        self.config = {"tesseract": str(pytesseract.get_tesseract_version())}

    def predict(self, image: Image.Image) -> list[Box]:
        data = self._tess.image_to_data(image, output_type=self._tess.Output.DICT)
        return boxes_from_ocr(data)
