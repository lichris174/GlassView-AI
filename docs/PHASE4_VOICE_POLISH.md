> **Historical (2026-06), superseded by [README.md](../README.md) and [DEVLOG.md](DEVLOG.md) as of 2026-10-22.** Kept for reference; this voice plan was never implemented (no `/transcribe` route, no `useVoice` hook) and is not on the current roadmap.

# Phase 4 - Voice + polish (plan)

Goal: local push-to-talk voice into the same chat path, plus the UX polish that
makes the product feel finished. Voice is local-only (Whisper), consistent with
the privacy stance.

## Voice input (push-to-talk)

Pipeline: hold key -> record mic -> transcribe locally -> feed text into the
existing `/chat` flow (no new answer path).

- **Capture (UI)**: `MediaRecorder` in the webview records WebM/Opus while a
  push-to-talk control is held (HUD mic button + a global "hold to talk" key).
  Stream chunks to the sidecar on release. Keep it in a `useVoice` hook so the
  capture logic is isolated from the glass components.
- **Transcribe (Python)**: `faster-whisper` (CTranslate2) is the pragmatic
  choice on Windows - fast on CPU, GPU optional, no PyTorch needed. New route
  `POST /transcribe` (multipart audio) -> `{ "text": ... }`. Model size routed
  by config (default `base.en`; allow `small`/`medium`).
  - Decision to lock with user: `faster-whisper` vs `openai-whisper` vs
    `whisper.cpp` binary. Recommend `faster-whisper` (speed + simple pip dep).
- **Wire**: transcript fills the composer / HUD ask box; user confirms or it
  auto-sends (setting). Reuses routing, OCR fusion, RAG exactly as typed input.
- **States**: idle / recording (level meter) / transcribing / error (mic
  permission denied, model missing). Mirror the streaming-answer affordances.

## Voice output (TTS) - optional, sequence after input

- Local TTS (`piper` is small and offline-friendly) reading the streamed answer.
- Toggle in settings; off by default. Stream sentence-by-sentence as tokens
  arrive so playback starts before the answer finishes.

## UX polish

- **Motion**: Framer Motion for HUD summon/dismiss, message enter, and the snip
  "lift" already prototyped. Respect `prefers-reduced-motion` everywhere.
- **States**: first-run empty state, per-message loading shimmer, inline error
  with retry, offline/model-missing banner driven by `/health`.
- **Keyboard-first**: full keyboard map (summon, snip, send, new chat, focus
  history, push-to-talk). Visible shortcut hints; a `?` cheatsheet overlay.
- **Multi-monitor correctness**: HUD and snip open on the monitor under the
  cursor (depends on the Rust capture change in the visual session).
- **Accessibility**: focus traps in HUD, ARIA roles on the chat log, contrast
  check on glass text (the reduced-transparency fallback already exists).

## New deps (Phase 4)

- Python: `faster-whisper` (+ ffmpeg runtime for decode), optional `piper-tts`.
- No new JS deps for capture (`MediaRecorder` is built in).

## Verification

- `POST /transcribe` returns text for a known WAV fixture (offline test with a
  tiny model, or mock the transcriber for unit tests + one real smoke test).
- Push-to-talk in the HUD transcribes and drives a normal streamed answer.
- Reduced-motion and keyboard-only walkthroughs pass.

## Build order

1. `/transcribe` route + transcriber module (testable in this kind of session).
2. `useVoice` hook + composer wiring (browser-testable for capture).
3. HUD push-to-talk + states (needs the visual/Tauri session).
4. TTS out (optional, last).
