# GlassView AI Backend

A local-first AI orchestration service that wraps Ollama. It exposes a small HTTP API -
streaming chat, per-chat SQLite history, RAG memory recall, model routing, OCR fusion,
and privacy redaction - so **any** frontend (Flutter, Tauri, Electron, web, CLI) can wire
into it. Everything runs on your machine; nothing leaves the device.

The frontend is intentionally not included here - this repo is the backend only, meant to
be paired with whatever UI you build on top of the HTTP API below.

## What's inside

```
glassview_ai/
  main.py          FastAPI app (endpoints below)
  config.py        settings + Ollama vision-model auto-detection
  db.py            SQLite chat store (per-chat history, no global session)
  ollama_client.py streaming Ollama client + message builder
  schemas.py       request/response models
  routing/         pick fast vs strong model per prompt/image
  ocr/             Tesseract text extraction + prompt fusion (no-op if absent)
  rag/             sqlite-vec memory store + embedders (offline HashEmbedder default)
  privacy/         secret/PII redaction applied before remembering
  agents/          bounded tool-use loop + tool registry
  evals/           scorer + runner + golden cases (make eval)
tests/             one suite per module
evals/             evaluation fixtures
```

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running, with a vision model pulled:
  `ollama pull qwen3-vl:8b`

The model is auto-detected at startup; override with `OLLAMA_MODEL`. Other env knobs:
`OLLAMA_HOST` (default `http://127.0.0.1:11434`), `GLASSVIEW_DB` (SQLite path).

## Setup & run

```powershell
./setup.ps1        # create .venv, install deps
./dev.ps1          # serve on http://127.0.0.1:8765 (uvicorn --reload)
```

## HTTP API

Base URL `http://127.0.0.1:8765`. CORS is open (`*`) for local frontends.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET  | `/health` | - | `{status, model, ollama_host}` |
| GET  | `/chats` | - | `{chats: [{id,title,updated_at,message_count}]}` |
| POST | `/chats` | `{title?}` | `{chat: ChatSummary}` |
| GET  | `/chats/{id}` | - | full chat with `messages` |
| PATCH| `/chats/{id}` | `{title}` | `{ok}` |
| DELETE | `/chats/{id}` | - | `{ok}` |
| POST | `/chats/{id}/clear` | - | `{ok}` |
| POST | `/chat` | `{chat_id, message, image?}` | **streamed** `text/plain` tokens |
| GET  | `/recall` | `?q=...&k=5` | `{hits: [{text,distance,meta,created_at}]}` |

Notes for integrators:
- `image` is a base64 string or data URL (`data:image/png;base64,...`) - there is no OS
  capture coupling; send whatever your frontend captures.
- `POST /chat` streams plain UTF-8 token chunks (read the response body as a stream).
  The turn is persisted and (on success) added to RAG memory automatically.
- `/recall` is semantic search over past turns ("what was that error yesterday").

## Tests & eval

```powershell
./.venv/Scripts/python.exe -m pytest      # all module suites
make eval                                  # eval harness (needs Ollama)
```
