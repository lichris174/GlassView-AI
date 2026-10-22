# GlassView

A desktop screen assistant (overlay + local API) whose real subject is an **on-device privacy
gate**: a small local detector that finds sensitive regions on a screenshot (credentials, API keys,
financial data, private messages, personal IDs) so they can be blurred or blocked *before* the
image is sent to a cloud vision model. Every claim about the gate is meant to be measured, not
asserted.

**Status (2026-10-22):** the assistant works end to end; the privacy gate does **not** exist yet.

| Phase | State |
|---|---|
| 0. Commit tree + critical fixes | Done |
| 1. Data pipeline (capture, splits, labels) | Done. 108 real frames from 9 sessions labeled; split frozen |
| 2. Eval harness + baselines (`block_all`, `ocr_regex`, `qwen_vl`) | Code done; no published baseline numbers yet |
| Synthetic training screens | Generator done |
| 3-6. Train detector, ONNX + benchmark, wire into app, report | Not started |

Until phase 5 lands, **no image is redacted**. Redaction today only applies to text written to the
recall memory. See [docs/DEVLOG.md](docs/DEVLOG.md) for the full log.

## Architecture

```
apps/desktop/    Tauri v2 + React 18 + TS overlay: pill -> toolbar (Chat, History, Settings,
                 region capture). Default hotkey Ctrl+Shift+Space (rebindable in Settings).
                 Starts the backend from .venv as a sidecar unless a GlassView backend
                 already answers on port 8765.
glassview_ai/    FastAPI service on http://127.0.0.1:8765
  main.py          routes (below)        config.py   env settings, Ollama model detection
  db.py            SQLite chat history   schemas.py  request/response models
  providers/       ollama | openai | anthropic | deepseek dispatch
  routing/ ocr/ rag/ privacy/ agents/ evals/
                   model routing, Tesseract OCR fusion, sqlite-vec memory,
                   text redaction, bounded tool-use loop, golden-case eval runner
ml/              privacy-gate pipeline: capture, splits, labels, synth/, metrics,
                 evaluate, baselines/
tests/           pytest suites for glassview_ai and ml
docs/            DEVLOG (source of truth), LABELING_GUIDE, COLLECTING
```

## Where your data goes

- **Local by default.** With no provider chosen, turns go to [Ollama](https://ollama.com) on this
  machine. Chat history (including screenshots) is stored in `glassview.db`, memory in
  `glassview.db.memories.db`, both next to the repo (override with `GLASSVIEW_DB`).
- **Cloud providers send your data off the device.** If you pick OpenAI, Anthropic, or DeepSeek
  in Settings, the question, OCR text from the screenshot, and chat history go to that provider,
  and vision providers (OpenAI, Anthropic) also receive the **unredacted screenshot**. The backend
  uses the API key for that request and never stores or logs it; the desktop app keeps it in plain
  text in the webview's localStorage. Nothing is filtered out of the image or the OCR text yet. That is the gap the privacy gate is meant to close.
- Ollama is **optional**: the backend starts without it, `/health` reports `degraded`, and cloud
  providers plus history keep working.

## Setup and run (Windows)

Prerequisites: Python 3.11+, Node 20+, Rust (for Tauri). Optional: Ollama with a vision model
(`ollama pull qwen3-vl:8b`, auto-detected; override with `OLLAMA_MODEL`), Tesseract for OCR.

```powershell
./setup.ps1                # .venv + backend/dev deps
./setup.ps1 -ML            # also ml extras (mss, faker, playwright) + Playwright Chromium
./dev.ps1                  # backend only: uvicorn --reload on 127.0.0.1:8765

cd apps/desktop
npm ci
npm run tauri dev          # desktop overlay (starts the backend from .venv; run ./setup.ps1 first)
npm run dev                # or: UI only in a browser at http://localhost:1420
```

Environment: `OLLAMA_HOST` (default `http://127.0.0.1:11434`), `OLLAMA_MODEL`, `GLASSVIEW_DB`,
`GLASSVIEW_ALLOWED_ORIGINS`, `GLASSVIEW_ALLOWED_HOSTS` (comma lists), and `GLASSVIEW_DATA` for the
ML dataset (see below).

## HTTP API

Base URL `http://127.0.0.1:8765`. No auth; the service is meant for loopback only:

- **CORS** allows only the desktop UI origins (`http://localhost:1420`, `http://127.0.0.1:1420`,
  `http://tauri.localhost`, `https://tauri.localhost`, `tauri://localhost`) and only the
  `Content-Type` header.
- **TrustedHost** rejects any `Host` other than `127.0.0.1` / `localhost` (DNS-rebinding guard).

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | - | `{status: "ok"\|"degraded", model, model_error, ollama_host, providers}` |
| GET | `/chats` | - | `{chats: [{id, title, updated_at, message_count}]}` |
| POST | `/chats` | `{title?}` | `{chat: {id, title, updated_at, message_count}}` |
| GET | `/chats/{id}` | - | `{id, title, created_at, updated_at, messages: [{role, content, images}]}`; 404 |
| PATCH | `/chats/{id}` | `{title}` | `{ok}`; 400 blank title, 404 unknown chat |
| DELETE | `/chats/{id}` | - | `{ok}`; 404 |
| POST | `/chats/{id}/clear` | `Content-Type: application/json` required (else 415) | `{ok}`; 404 unknown chat |
| POST | `/chat` | `{chat_id, message="", image?, redact=true, recall=true, provider?, api_key?, model?}` | streamed `text/plain` chunks (not SSE) |
| POST | `/agent` | `{question, max_steps=4 (1-8, else 422)}` | `{answer, steps: [{tool, args, observation}], stopped_reason, tools}` |
| GET | `/recall` | `?q=...` (required) `&k=5` (1-50, else 422) | `{hits: [{text, distance, meta, created_at}]}` |

`/chat` details:
- `image` is a data URL or bare base64. Omit it to reuse the chat's last image.
- `provider` is one of `ollama`, `openai`, `anthropic`, `deepseek`. If omitted or unrecognized, it is guessed from
  the key prefix (`sk-ant-` Anthropic, `sk-` OpenAI, otherwise Ollama). `model` overrides the
  cloud model.
- `redact` controls whether secrets/PII are scrubbed from the text saved to memory; `recall` folds
  relevant notes from other chats into the prompt.
- Errors before streaming: 400 missing API key or undecodable image, 422 invalid body, 501 provider
  SDK not installed, 503 no local model; nothing is saved. Errors mid-stream arrive inline as
  `[error] ...`; mid-stream failures and cancellations are still saved to history (but not replayed
  to the model).

`/agent` runs the bounded tool-use loop on the local Ollama model only (502 if the model call
fails, 503 if no local model).

## ML pipeline (privacy gate)

Needs `./setup.ps1 -ML` (or `pip install -r requirements-ml.txt` and
`python -m playwright install chromium`). The dataset lives **outside the repo**:
`GLASSVIEW_DATA` if set, otherwise `%LOCALAPPDATA%\GlassView\dataset`.

- [docs/COLLECTING.md](docs/COLLECTING.md): capture checklist for the real val/test screenshots.
- [docs/LABELING_GUIDE.md](docs/LABELING_GUIDE.md): class definitions and labeling rules.
- `make split` / `make verify-split`: freeze and check the session-level split.
- `make baselines SPLIT=val`: run the three baselines; each run writes `results/<stamp>-<system>-<split>/`.

## Tests and checks

```powershell
./.venv/Scripts/python.exe -m pytest -q                     # or: make test
./.venv/Scripts/python.exe -m ruff check glassview_ai ml tests   # or: make lint
cd apps/desktop; npx tsc --noEmit
make eval                                                    # live golden eval, needs Ollama
```

CI (`.github/workflows/ci.yml`) runs pytest + ruff (Python 3.12) and the desktop type check on
pushes to `main` and on pull requests.
