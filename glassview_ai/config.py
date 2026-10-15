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

# Env is read at call time (see load_settings / detect_model) so that tests and
# the launcher can set GLASSVIEW_DB / OLLAMA_HOST before values are resolved.

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


# Origins the desktop UI is served from: the Vite dev server, and the Tauri v2
# webview (http://tauri.localhost on Windows, tauri://localhost on macOS/Linux).
_DEFAULT_ORIGINS = (
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
)
_DEFAULT_HOSTS = ("127.0.0.1", "localhost")


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def allowed_origins() -> tuple[str, ...]:
    """Browser origins allowed to call the API (override: GLASSVIEW_ALLOWED_ORIGINS)."""
    return _env_list("GLASSVIEW_ALLOWED_ORIGINS", _DEFAULT_ORIGINS)


def allowed_hosts() -> tuple[str, ...]:
    """Host headers accepted (override: GLASSVIEW_ALLOWED_HOSTS). Loopback only."""
    return _env_list("GLASSVIEW_ALLOWED_HOSTS", _DEFAULT_HOSTS)


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    # None when Ollama is down or has no vision model at startup. The app still
    # serves cloud providers and history; the local model is re-detected later.
    model: str | None
    db_path: str
    model_error: str | None = None


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


def load_settings(*, require_model: bool = False) -> Settings:
    """Resolve settings. A missing local model is recorded, not fatal, unless
    ``require_model`` is set (the offline eval runner needs a real model)."""
    host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
    db_path = os.environ.get("GLASSVIEW_DB", DEFAULT_DB_PATH)
    try:
        model, error = detect_model(host), None
    except ModelNotFoundError as exc:
        if require_model:
            raise
        model, error = None, str(exc)
    return Settings(ollama_host=host, model=model, db_path=db_path, model_error=error)
