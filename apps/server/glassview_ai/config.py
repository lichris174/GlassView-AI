"""Runtime configuration + Ollama model auto-detection.

The old prototype hardcoded ``qwen3-vl:8b-instruct`` which did not match the
installed tag (``qwen3-vl:8b``), so a fresh clone failed. Here we detect an
installed vision model at startup and fail loudly with a helpful message if none
is present, instead of silently 404ing mid-request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "glassview.db"
)

# Env is read at call time (see load_settings / detect_model), not bound here at
# import: binding at import froze the values before tests or the launcher could
# set GLASSVIEW_DB / OLLAMA_HOST, so overrides were silently ignored.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)

# Preference order when several vision tags are installed. We prefer instruct
# tunes, then any qwen3-vl, then any model the user explicitly named.
_VISION_PREFERENCES = ("qwen3-vl",)

MAX_HISTORY_TURNS = 12  # user/assistant pairs kept as rolling context

SYSTEM_PROMPT = (
    "You are GlassView, a local screen assistant. Respond directly and clearly "
    "in Markdown. Use bullet points for lists and LaTeX for math (inline $...$ "
    "or block $$...$$). Do not include chain-of-thought or meta commentary; just "
    "answer the user."
)


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    model: str
    db_path: str


class ModelNotFoundError(RuntimeError):
    """Raised when no usable vision model is installed in Ollama."""


def _list_installed_models(host: str) -> list[str]:
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:  # daemon down or unreachable
        raise ModelNotFoundError(
            f"Cannot reach Ollama at {host}. Is the daemon running "
            f"('ollama serve')? Underlying error: {exc}"
        ) from exc
    data = resp.json()
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def detect_model(host: str | None = None, override: str | None = None) -> str:
    """Pick the model to use.

    Order: explicit override (env ``OLLAMA_MODEL`` or arg) if installed, else a
    preferred vision family (instruct first), else raise with guidance.
    """
    host = host or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    override = override or os.environ.get("OLLAMA_MODEL")
    installed = _list_installed_models(host)

    if override:
        if override in installed:
            return override
        # Allow a bare family name to match a concrete tag (qwen3-vl -> qwen3-vl:8b)
        match = next((m for m in installed if m.startswith(override)), None)
        if match:
            return match
        raise ModelNotFoundError(
            f"Requested model '{override}' is not installed. Installed: "
            f"{installed or '(none)'}. Pull it with 'ollama pull {override}'."
        )

    for family in _VISION_PREFERENCES:
        # Prefer an instruct tune within the family if available.
        instruct = next(
            (m for m in installed if m.startswith(family) and "instruct" in m), None
        )
        if instruct:
            return instruct
        any_tag = next((m for m in installed if m.startswith(family)), None)
        if any_tag:
            return any_tag

    raise ModelNotFoundError(
        "No vision model found. Pull one with 'ollama pull qwen3-vl:8b' "
        f"(installed models: {installed or '(none)'})."
    )


def load_settings() -> Settings:
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    return Settings(
        ollama_host=host,
        model=detect_model(host),
        db_path=os.environ.get("GLASSVIEW_DB", DEFAULT_DB_PATH),
    )
