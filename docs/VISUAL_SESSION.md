# Visual / Tauri session - prep checklist

Everything below needs a real browser or the native Tauri runtime, so it was
deferred from headless sessions. This doc makes the next session turnkey.

## Preconditions

- Ollama running with a vision tag pulled: `ollama pull qwen3-vl:8b`.
- One-time: `./setup.ps1` (npm install + venv + deps).
- Run native app: `./dev.ps1` (Vite + Python sidecar + Tauri shell).
- Glass/overlay in a plain browser (cheap iteration):
  `npm --prefix apps/ui run dev` then open
  - `http://localhost:1420/preview.html` (glass material + tuning sliders)
  - `http://localhost:1420/overlay.html` (snip overlay; synthetic frame outside Tauri)
- Optional automated checks: install the Playwright MCP Bridge browser
  extension, OR use headless `npx playwright` screenshots. Without one of these
  there is no automated visual verification.

## 1. Snip overlay - runtime verification (built, untested live)

Code: `apps/ui/src/overlay/` + Rust commands in `apps/shell/src/capture.rs`.
Verify under Tauri:
- Drag selection; scrim punch-through shows full brightness inside.
- Loupe follows cursor; color/coords read correct pixels.
- Keyboard: arrows nudge, shift+arrows resize, alt = 1px, Enter confirm, Esc cancel.
- Crop accuracy: selected region matches what lands in the composer (check the
  `scale = image px / CSS px` math against the actual DPR).
- Lift-out animation plays before the window closes.

## 2. Multi-monitor capture (Rust change)

Today `capture.rs` uses `Screen::from_point(0,0)` (primary only). Change:
- Capture the monitor under the cursor (`Screen::from_point(cursor_x, cursor_y)`).
- Place the snip overlay window on that monitor (position + size to its bounds).
- Same for the HUD summon. Verify on a 2-monitor setup with different DPRs.

## 3. Real liquid-glass lensing (visual, subjective)

Isolated to `apps/ui/src/glass/`. Plan: `backdrop-filter` + SVG
`feDisplacementMap` refraction at the edges + layered specular + optional WebGL
edge-glint; in the HUD, feed the live screen capture as the backdrop texture.
This is a taste call - iterate in `preview.html` with sliders, then lock tokens.
Do NOT build blind; needs eyes on it.

## 4. HUD overlay (Phase 2, if not yet built)

Summon-on-hotkey glass capsule, captures monitor under cursor, ask box, inline
streamed answer, dismiss -> click-through. Reuses `tauri-plugin-global-shortcut`.

## 5. Real agent tools (need native)

The tool registry (`glassview_ai/agents/`) has stub/injectable tools. Add real
ones that require Tauri: read clipboard, crop/zoom a region of the last capture.
Wire them so the agent loop can call them during `/chat`.

## 6. Phase 4 voice (browser-testable parts)

`MediaRecorder` capture + `useVoice` hook can be built/tested in the browser;
HUD push-to-talk needs the native window. See `PHASE4_VOICE_POLISH.md`.

## Server state going in

- Spine wired into `/chat` (OCR fuse -> route -> RAG persist) and `/recall` live.
- 31 server tests + ruff green; UI build + typecheck + vitest green.
- Routing currently has one model tag (fast == strong); add a small fast model
  to make escalation real.
- OCR is dormant until a Tesseract binary is installed (`choco install
  tesseract` or the UB-Mannheim installer), then it activates automatically.
