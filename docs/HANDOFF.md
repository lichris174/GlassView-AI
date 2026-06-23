# GlassView - session handoff

State snapshot for continuing the rebuild in a fresh session.

## What this is

Local-first screen copilot. Hotkey -> capture screen -> a local vision model
(Ollama qwen3-vl) reasons about it. Being rebuilt from a prototype into a
portfolio piece that shows full-stack + applied-AI + systems engineering.

Thesis: capture -> an AI that reasons about the screen, acts on it (tool use),
and remembers it (RAG), delivered through a liquid-glass HUD overlay with voice.

## Stack and layout

- `apps/shell` - Tauri (Rust). Capture, region snip, global hotkey, window
  effects, owns the Python sidecar. Split into `capture.rs`, `window_fx.rs`,
  `sidecar.rs`, `main.rs`.
- `apps/ui` - React + Vite + TypeScript. Chat UI, streaming, history. Glass
  material isolated in `src/glass/` (GlassSurface + glass.css) and tokens in
  `src/styles/tokens.css`. Browser preview in `src/preview/` (preview.html).
- `apps/server` - FastAPI (Python). Streaming `/chat`, SQLite per-chat history,
  Ollama client, startup model auto-detection. Venv at `apps/server/.venv`.

Working branch: `rebuild/glassview`.

## Run

```powershell
./setup.ps1     # one-time: npm install + python venv + deps
./dev.ps1       # tauri dev: starts Vite + Python sidecar + native shell
```

Glass material preview (browser only, cheap to iterate):

```powershell
npm --prefix apps/ui run dev
# open http://localhost:1420/preview.html
```

Prereq: Ollama running with a vision model pulled (`ollama pull qwen3-vl:8b`).
The server auto-detects the installed tag; no env override needed.

## Done

- Phase 0: monorepo restructure, removed duplicate frontends + committed chat
  data, fixed broken model-name onboarding. Committed `ce109fc`.
- Phase 1 core loop: FastAPI streaming + SQLite (no global session), React
  streaming UI, Tauri owns sidecar. Verified live end to end (window + sidecar
  + Ollama, health + chats 200). Backend tests, UI build + test, cargo check
  all green.
- Glass material: premium CSS frost (blur, saturate, brightness, specular,
  grain) with tunable tokens, plus a browser preview with live tuning sliders.
- Snip overlay rebuilt as a React Vite entry (`apps/ui/overlay.html` +
  `src/overlay/`), replacing the old vanilla `public/overlay.html` (deleted).
  Freeze-frame, scrim fade-in (180ms), box-shadow punch-through to full
  brightness, tabular W x H px badge, magnifier loupe with pixel color/coords,
  keyboard nudge (arrows) / resize (shift+arrows) / Enter confirm / Esc cancel,
  exit "lift" animation. Browser-previewable via a synthetic frame when not in
  Tauri (open http://localhost:1420/overlay.html under `npm run dev`). Bridge
  helpers added to `lib/tauri.ts` (getSnipImage/finishSnip/cancelSnip). Vite
  rollup input now includes overlay. Build + typecheck + vitest green.

## Open / next

1. Snip overlay: runtime-verify under Tauri (`./dev.ps1`) - drag, loupe color
   sampling, keyboard adjust, lift exit, crop accuracy. Then multi-monitor:
   Rust still captures the primary screen (`Screen::from_point(0,0)`); make it
   capture the monitor under the cursor and place the overlay window there.
2. Apple liquid glass (real lensing/refraction): WebGL shader sampling a
   backdrop texture; HUD overlay feeds the screen capture as that texture.
   Swap happens inside `src/glass/` only.
3. Applied-AI spine: DONE as standalone, offline-tested modules (30 server
   tests, ruff green). Still UNWIRED into the `/chat` route and the UI.
   - `glassview_ai/evals/` - scorer + `run_eval` + live Ollama runner, golden
     set at `evals/golden/cases.json`, `make eval` target.
   - `glassview_ai/privacy/` - `redact()` masks secrets/PII (used by RAG add).
   - `glassview_ai/routing/` - `route()` fast vs strong model by prompt/image.
   - `glassview_ai/agents/` - bounded tool-use loop + `ToolRegistry` (tools are
     stubs/injectable; real clipboard/crop tools need Tauri wiring).
   - `glassview_ai/rag/` - sqlite-vec `MemoryStore` + pluggable embedder
     (offline `HashEmbedder`, `OllamaEmbedder` for quality).
   - `glassview_ai/ocr/` - Tesseract extract (graceful if binary absent; not
     installed here) + `fuse_prompt`.
   Next: wire spine into `/chat` (OCR fuse -> route -> optional agent loop ->
   persist+redact into RAG), expose `/recall`, add real agent tools via Tauri,
   and add image golden cases (Pillow now installed, can synthesize fixtures).
4. Done: the `POST /chat` empty-body bug. Two causes. (a) `config` bound
   `DB_PATH`/`OLLAMA_HOST` from env at import time, so the launcher's and the
   tests' `GLASSVIEW_DB` override was ignored; `load_settings`/`detect_model`
   now read env at call time, and the test suite is properly isolated (was
   silently appending to a real `glassview.db`). (b) an Ollama error raised
   mid-stream after the 200 header reached the client as a silent empty body;
   `event_stream` now catches it, emits `[error] ...` into the stream, and
   persists the failed turn. A regression test covers the error path. Next live
   run will show the real Ollama error string if one occurs.

Build order preference: finish the UI (glass + snip) before wiring AI.

## Conventions (important)

- No AI tells in committed code/docs: no em dashes, en dashes, unicode ellipsis,
  smart quotes, emojis, or giveaway phrasing. Plain ASCII punctuation.
- Commits do NOT include a Co-Authored-By Claude trailer (must not look AI made).
- Keep the design/UI layer swappable: components consume tokens, glass lives
  behind one module, logic decoupled from presentation.
- Work autonomously through mechanical steps; pause only at subjective UI/visual
  design choices.

Full plan: `C:\Users\lichr\.claude\plans\temporal-sparking-bengio.md` (private).
