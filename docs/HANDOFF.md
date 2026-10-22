> **Historical (2026-06), superseded by [README.md](../README.md) and [DEVLOG.md](DEVLOG.md) as of 2026-10-22.** Kept for reference; the backend is no longer Ollama-only, everything is committed, and the Voice panel listed here was removed in `2cf84ae` (2026-10-14).

# GlassView — Session Handoff

_Last updated: 2026-06-25. Status: Milestones A/B/C done and working, including region capture._

## What this is
A Tauri v2 + React 18 + TS desktop overlay ("GlassView") that wraps the existing
FastAPI + Ollama backend. A draggable bottom-right pill expands into a toolbar; tools open
glass panels (Chat, Voice, History, Settings) above the pill. Region capture floats the
whole window to select a screen area and ask about it.

## Layout
- **Frontend:** `apps/desktop/`
  - `src/` — React app (Vite). Entry `src/main.tsx` → `App.tsx`.
  - `src-tauri/` — Rust shell (`main.rs`, `capture.rs`, `sidecar.rs`).
- **Backend (unchanged):** repo root `glassview_ai/` — FastAPI on `http://127.0.0.1:8765`.
  README has the endpoint table. `/chat` streams plain `text/plain` token chunks (not SSE);
  omitting `image` reuses the chat's last image.
- **Brief + visual reference:** `docs/files/GLASSVIEW_FRONTEND.md` + `docs/files/glassview-mockup.jsx`.
- **Plan:** was a local Claude Code plan file (`~/.claude/plans/read-everything-in-c-users-lichr-onedriv-fuzzy-parasol.md`); it is not in the repo and no longer exists.

## How to run
```
cd apps/desktop && npm run tauri dev    # native overlay (auto-starts backend if 8765 idle)
# or
cd apps/desktop && npm run dev          # browser-only at localhost:1420 (no native shell)
```
Native window can't be screenshotted from the CLI env — must be run on a real desktop.
Needs Ollama running with `qwen3-vl:8b` (already installed). `cargo build` first run is slow
(~2 min, 195 crates); incremental ~15-45s.

## Done (Milestones A/B/C)
- **A** Pill + toolbar + theme. CSS-var theming (`styles/tokens.ts` → `--gv-*`, `useTheme`).
  Whole G logo is a drag handle (click vs drag via threshold; native drag in Tauri).
- **B** Chat (streaming `/chat`, `useChat` + `api/client.ts`), History (`/chats`), Settings
  (provider auto-detect + badge, shortcut rebind), Error/health fallback (`useHealth`).
- **C** Native shell:
  - Content-sized transparent always-on-top window, **logo anchored bottom-left**, grows for
    toolbar/panel via `lib/tauri.ts` `fitWindowToContent` + ResizeObserver. Anchor follows
    user drags (`watchWindowMoves`). NOT fullscreen (avoids click-through trap).
  - Global `Ctrl+Shift+Space` toggle, system tray (Show/Quit), sidecar auto-spawns backend
    if 8765 idle and kills on exit.
  - **Region capture (rebuilt safe):** runs INSIDE the main window — capture in Rust
    (`capture_screen`), fullscreen the main window, select + crop in JS canvas
    (`components/RegionSelect.tsx`, HiDPI-aware), open Chat with the crop. THREE escapes:
    Rust global `Escape` failsafe (`arm/disarm_region_escape`, works even if webview frozen),
    React Esc, Cancel button. See the memory note overlay-no-unescapable-fullscreen — do NOT
    reintroduce a second fullscreen window.
  - Voice (`VoicePanel`) via Web Speech API.
  - All native calls gated by `isTauri()` so the browser build still runs.

## Known gaps / next (Milestone D + follow-ups)
1. **Cloud providers are frontend-only.** Settings captures an OpenAI/Anthropic key and shows
   a badge, but the **backend is Ollama-only** — those turns still run locally. To make cloud
   real: extend `glassview_ai/schemas.py` `ChatRequest` + `routing/` + `ollama_client` to
   dispatch by provider, and have the frontend send `provider`/`api_key` on `/chat`.
2. **Chat context strip is a placeholder** ("No context captured") until live window-context
   capture is wired.
3. **Milestone D polish:** notif pulse is wired; remaining is tray polish + animation tuning.
4. **Nothing is committed** — all work is uncommitted in the working tree on branch
   `rebuild/glassview`. There's also stale deleted `apps/server`/`apps/shell`/old `apps/ui`
   from the prior restructure still showing in `git status` (the new app is `apps/desktop`).
5. `auto-launch` setting toggle is UI-only (no `tauri-plugin-autostart` wired yet).

## Gotchas
- **Overlay sizing:** the panel is out-of-flow, so the window fit re-runs on `expanded`/
  `activeTool` changes (a plain ResizeObserver won't fire when the panel mounts). Sizes use
  `offsetWidth/Height` (transform-independent) so the scale-in animation doesn't mis-measure.
- **HiDPI:** test machine is scale=2 (1280×800 logical / 2560×1600 physical). Region crop
  scales CSS px → physical via `naturalWidth/innerWidth`.
- **Region safety is non-negotiable** — keep the Rust global-Esc failsafe; never ship a
  fullscreen/always-on-top window that can render blank without an OS-level escape.
- `screenshots` crate v0.7 verified working on this PC (`src-tauri/examples/captest.rs`).

## Verify quickly
- Chat: open Chat, send a message, watch tokens stream; reopen History → chat saved.
- Region: Region tool → drag a box → Chat opens with the capture; press Esc anytime to bail.
- Health: stop Ollama → ErrorPanel within ~10s; restart → clears.
