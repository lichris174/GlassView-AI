"""Systems the trained detector is compared against.

Each system is built lazily so that, for example, running the OCR baseline
does not require a GPU stack or a running Ollama.

| name       | what it is                                          | why it is here            |
|------------|-----------------------------------------------------|---------------------------|
| block_all  | one box covering every frame                        | the privacy-maximal floor |
| ocr_regex  | Tesseract words + the app's existing regex rules    | what GlassView does today |
| qwen_vl    | qwen3-vl 8B via Ollama, prompted for boxes          | the large model to match  |
"""

from __future__ import annotations

from collections.abc import Callable

from ..evaluate import Predictor


def _block_all() -> Predictor:
    from .block_all import BlockAll

    return BlockAll()


def _ocr_regex() -> Predictor:
    from .ocr_regex import OcrRegex

    return OcrRegex()


def _qwen_vl() -> Predictor:
    from .qwen_vl import QwenVL

    return QwenVL()


SYSTEMS: dict[str, Callable[[], Predictor]] = {
    "block_all": _block_all,
    "ocr_regex": _ocr_regex,
    "qwen_vl": _qwen_vl,
}


def build(name: str) -> Predictor:
    return SYSTEMS[name]()
