# GlassView

A local-first screen copilot. Capture your screen with a hotkey and ask a local
vision model about it. Everything runs on your machine through Ollama, so nothing
leaves the device.

This repository is a rebuild of an earlier prototype. The goal is a clean,
three-layer architecture: a native shell for capture and window control, a React
UI, and a Python service that handles the AI work.

## Status

Core loop is working: screen capture, streaming chat against a local vision model,
and per-chat history. The applied-AI features (OCR fusion, tool use, memory recall,
evaluation harness) and the glass HUD overlay are in progress.

## Architecture

```
apps/shell    Tauri (Rust)    global hotkey, screen capture, region snip, window effects,
                              and the lifecycle of the Python service
apps/ui       React + Vite    chat UI with streaming, history, Markdown and LaTeX
apps/server   FastAPI (Py)    streaming chat, SQLite history, Ollama client
```

The shell owns the Python service: it starts it on launch and stops it on exit.
State lives in SQLite, scoped per chat, so multiple windows or concurrent requests
stay isolated.

## Prerequisites

- [Ollama](https://ollama.com) running, with a vision model pulled:
  `ollama pull qwen3-vl:8b`
- Rust and cargo, plus the Tauri CLI: `cargo install tauri-cli`
- Node.js 18 or newer
- Python 3.11 or newer

The server detects an installed vision model at startup, so you do not need to
configure a model name by hand. Override it with `OLLAMA_MODEL` if you want a
specific tag.

## Setup

```powershell
./setup.ps1
```

This installs the UI dependencies and creates the Python virtual environment.

## Run

```powershell
./dev.ps1
```

The Tauri shell starts the Vite dev server and the Python service for you.

## Hotkey

`Ctrl+Alt+Shift+M` brings the window forward and starts a region capture from
anywhere.

## Layout

```
apps/
  shell/    Rust shell (Tauri)
  ui/       React frontend
  server/   FastAPI backend
evals/      evaluation fixtures
docs/       notes and diagrams
```

## Tests

```powershell
# backend
cd apps/server; ./.venv/Scripts/python.exe -m pytest

# frontend
cd apps/ui; npm test
```
