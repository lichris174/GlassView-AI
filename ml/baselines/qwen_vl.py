"""Baseline: ask the 8B vision-language model to box sensitive regions, zero-shot.

This is the "giant" the small detector is meant to match at a fraction of the
cost. It gets the same class definitions as the labeling guide, at temperature
0, and must answer with JSON boxes. Qwen3-VL reports coordinates on a 0-1000
grid relative to the image, which is converted back to pixels here.

The model gives no confidence scores, so every box scores 1.0: its AP is a
single operating point, and its privacy metrics are the fair comparison.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json

import httpx
from PIL import Image

from glassview_ai import config as app_config

from ..labels import CLASSES, Box

PROMPT = """Find every region of this screenshot that would be harmful to send to a third party.
Use exactly these labels:
- credential: filled password fields, visible passwords, one-time or recovery codes
- api_key: API keys, tokens, secrets, private keys, connection strings with passwords
- financial: card numbers, account or routing numbers, IBANs, account balances, transactions
- private_message: message bodies in chat or email apps, including inbox previews
- personal_id: faces, ID documents, government ID numbers, home addresses, dates of birth

Answer with only a JSON array, one object per region:
[{"label": "<label>", "bbox_2d": [x1, y1, x2, y2]}]
Coordinates are on a 0-1000 grid relative to the image width and height.
If nothing is sensitive, answer [].""".strip()

GRID = 1000.0
MAX_TOKENS = 1024


def _json_objects(text: str) -> list[dict]:
    """Every complete JSON object in the text, in order.

    Decoding object by object (rather than one array) salvages the boxes from a
    reply that was cut off by the token limit or wrapped in chatter that itself
    contains brackets.
    """
    decoder, out, i = json.JSONDecoder(), [], 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        i = end
    return out


def parse_boxes(text: str, width: int, height: int) -> list[Box]:
    """Extract boxes from the model's reply; tolerant of code fences and chatter."""
    boxes = []
    for item in _json_objects(text):
        coords = item.get("bbox_2d") or item.get("bbox")
        if not (isinstance(coords, list) and len(coords) == 4):
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in coords)
        except (TypeError, ValueError):
            continue
        label = str(item.get("label", "")).strip().lower().replace(" ", "_")
        # Privacy metrics ignore the class; an unknown label still blurs.
        cls = label if label in CLASSES else CLASSES[0]
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        boxes.append(Box(
            cls,
            max(0.0, x1 / GRID * width), max(0.0, y1 / GRID * height),
            min(float(width), x2 / GRID * width), min(float(height), y2 / GRID * height),
        ))
    return boxes


class QwenVL:
    name = "qwen_vl"

    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        import os

        self.host = host or os.environ.get("OLLAMA_HOST", app_config.DEFAULT_OLLAMA_HOST)
        self.model = model or app_config.detect_model(self.host)
        self._http = httpx.Client(timeout=600.0)
        self.config = {
            "model": self.model,
            "model_digest": self._digest(),
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest()[:16],
            "temperature": 0,
            "seed": 0,
            "num_predict": MAX_TOKENS,
            # Replies with no usable box that also weren't a clean "[]". A high
            # count means the baseline lost recall to formatting, not to vision.
            "unparsed_replies": 0,
        }

    def _digest(self) -> str:
        """Exact weights identity: a tag like ':8b' can be re-pulled to new weights."""
        tags = self._http.get(f"{self.host}/api/tags").json().get("models", [])
        return next((m.get("digest", "") for m in tags if m.get("name") == self.model), "")

    def predict(self, image: Image.Image) -> list[Box]:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "seed": 0, "num_predict": MAX_TOKENS},
            "messages": [{
                "role": "user",
                "content": PROMPT,
                "images": [base64.b64encode(buf.getvalue()).decode("ascii")],
            }],
        }
        resp = self._http.post(f"{self.host}/api/chat", json=payload)
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "")
        boxes = parse_boxes(reply, image.width, image.height)
        if not boxes and reply.strip().strip("`").removeprefix("json").strip() != "[]":
            self.config["unparsed_replies"] += 1
        return boxes
