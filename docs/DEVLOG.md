# GlassView Dev Log

A running record of what was built, what was decided, and why. Newest entries at the bottom.
Numbers that appear here are only ever copied from a run file; none are estimates.

---

## 2026-10-13 — Audit and repositioning

### Where the project stood
GlassView is a desktop screen assistant: a Tauri (Rust) overlay with a React UI, talking to a local
FastAPI backend that sends screenshots plus a question to a vision-language model (Ollama
`qwen3-vl:8b` locally, or OpenAI / Anthropic / DeepSeek in the cloud).

A full audit found the app worked but read as "an Ollama wrapper with screenshots", and most of the
recent work was uncommitted. Highest-severity issues found:

| Severity | Issue | Where |
|---|---|---|
| Critical | CORS `*` with no auth: any website could read, delete, or drive chats on `127.0.0.1:8765` | `glassview_ai/main.py` |
| High | Backend refuses to start without Ollama, even when using a cloud provider | `main.py` lifespan → `detect_model` |
| High | Typing while a reply streams triggers tool hotkeys (C/R/H/S) | `apps/desktop/src/App.tsx` keydown |
| High | Cancelling a reply can append `[cancelled]` text into a *different* chat; no real request abort | `hooks/useChat.ts` |
| High | Most new code untracked in git; HEAD could not build | repo |

### The pivot
Goal: make the project demonstrate AI/ML skill (target roles: AI/ML and hardware), with every claim
backed by a measurement.

Options considered and rejected:
- **Prompt-injection defenses.** The local model has no system access, so the worst case is a wrong
  answer. Weak story.
- **Terminal-error detector.** Too niche; large general models already do this well and cheaply.
- **Screen-context classifier** (code editor / terminal / browser…). Its output would only pick a
  system prompt, which barely changes behavior. A model is only worth training if its output
  changes what the app *does*.

**Chosen: an on-device privacy gate.** A small trained detector finds sensitive regions on screen
(credentials, API keys/tokens, financial numbers, private messages, faces/IDs) so the app can blur
them, or block the request, *before* a screenshot is sent to a cloud model.

Why this needs a small local model: you can't ask a cloud model whether it is safe to send something
to a cloud model. The check has to run locally, on every capture, in milliseconds.

### How it will be measured
- **Test set:** ~300 hand-labeled screenshots, test split frozen and hashed before any training.
  Sensitive content is created with fake accounts and data only.
- **Primary metric:** per-class recall. Missing a secret is worse than over-blurring, so plain
  accuracy is the wrong number.
- **Also:** false-blur rate; end-to-end answer quality with blurred vs. original screenshots;
  latency per frame on GPU (RTX 5060) and CPU.
- **Baselines:** the existing OCR + regex redaction, "block every cloud call", qwen3-vl 8B prompted
  zero-shot, and Grounding DINO / OWLv2.
- **Rigor:** 95% bootstrap confidence intervals, paired significance tests, run manifests
  (git sha, model hash, dataset hash).
- **Deployment:** ONNX Runtime on GPU and CPU, FP32 → FP16 → INT8. The NPU was dropped to keep scope
  tight.

### Plan
| Phase | Work |
|---|---|
| 0 | Commit the tree; fix critical bugs |
| 1 | Capture tool, labeling guide, label ~300 images, freeze test split |
| 2 | Eval harness and baselines |
| 3 | Train detector (a few model sizes) |
| 4 | ONNX export, quantization, GPU/CPU benchmarks |
| 5 | Wire into app (blur/block setting), end-to-end answer-quality eval |
| 6 | Report page, README |

---

## 2026-10-14 — Phase 0: commit the tree

Verified the working tree builds before committing: `pytest` (64 passed), `tsc --noEmit` (clean),
`cargo check` (clean). Scanned staged files for secrets; only placeholder strings found.

Rewrote `.gitignore` for the current layout and made sure captured screenshots, local databases,
build output, and the venv can never be committed. That rule matters more from Phase 1 on, when the
repo will sit next to a folder of screenshots that contain (fake) sensitive data.

Commits:
- `d9a3b5a` chore: update .gitignore for desktop + root backend layout
- `ca0fef4` refactor: move backend from apps/server to repo root
- `2cf84ae` refactor: replace apps/shell + apps/ui with unified apps/desktop
- `08ddb0a` docs: update README/handoff, add frontend brief

Next: critical bug fixes, each as its own commit with a test.

---

## 2026-10-14 — Phase 0: critical bug fixes

### 1. Any website could drive the local API
**Bug.** The backend allowed CORS from `*` with no auth. A page open in the user's browser could
call `127.0.0.1:8765` to read every chat (including screenshots), delete history, or send prompts.

**Fix.** Two layers:
- *Origin allowlist* (`config.allowed_origins()`): only the Vite dev server and the Tauri webview
  origins. Browsers block other sites from reading responses and from sending preflighted requests
  (`DELETE`, JSON `POST`).
- *Host check* (`TrustedHostMiddleware`, loopback only). This blocks DNS rebinding, where an
  attacker's domain re-resolves to `127.0.0.1` so the browser treats it as same-origin and CORS
  never applies. The `Host` header still carries the attacker's domain, so it is rejected.

**Considered, skipped:** a per-session auth token. It defends against other programs on the same
machine, but those already run as the user and can read `glassview.db` directly, so the token
would add complexity without closing a real gap.

**Tests:** desktop origin allowed; foreign origin gets no CORS header and a failed preflight;
non-loopback `Host` returns 400.

### 2. Backend refused to start without Ollama
**Bug.** Startup called `detect_model()`, which raised if Ollama was not running, even for users
on a cloud provider who never touch the local model. `/health` also never re-checked, so starting
Ollama later required restarting the backend.

**Fix.** A missing model is now recorded (`model=None`, `model_error`) instead of crashing.
`/health` re-probes Ollama on each poll (in a worker thread, so a slow daemon can't stall other
requests) and reports `"degraded"` with the reason. Local `/chat` and `/agent` return `503` with
that reason; cloud providers work regardless. The offline eval runner still requires a real model
(`load_settings(require_model=True)`).

### 3. Typing during a reply triggered tool shortcuts
**Bug.** The chat input was `disabled` while a reply streamed. Disabling an element drops its
focus to the page, so the next letters typed hit the global C/R/H/S tool hotkeys and opened
other panels.

**Fix.** The input stays enabled (sending is still blocked while busy, so the next question can be
typed early). The hotkey handler now ignores any text-entry target and any Ctrl/Alt/Meta combo.

### 4. Cancelled replies leaked into other chats
**Bug.** `useChat` used one shared `cancelled` flag and never aborted the HTTP request. Opening a
different chat mid-reply set the flag, but a new turn reset it, so the old stream could append its
`[cancelled]` text into the newly opened chat. The old request also kept generating in the
background.

**Fix.** Each turn gets a generation number and its own `AbortController`. Switching or resetting
the chat bumps the generation and aborts the request; a turn only touches state if it is still the
current generation. On the backend, an aborted stream now saves the partial answer marked
`[cancelled]`. The save is wrapped in `asyncio.shield` because the request task is being cancelled
at that moment, and an unshielded `await` would silently drop the turn.

**Tests:** backend test closes the stream after the first token and checks the turn is stored as
`Hello\n\n[cancelled]`. The frontend has no test runner yet; these changes were verified with
`tsc` and a production build.

**Results:** `pytest` 71 passed, `ruff` clean, `tsc` clean, `vite build` OK.

### Independent review
A separate reviewer agent read the diff cold. It confirmed the Tauri origins, middleware order,
provider resolution, and the `asyncio.shield` handling, and found nothing blocking. Fixed from its
findings:
- `POST /chats/{id}/clear` takes no body, so a cross-site page could send it as a "simple" request
  that skips the CORS preflight. Bodyless POSTs now require `Content-Type: application/json`
  (415 otherwise), which forces a preflight. *Test added.*
- With focus now staying in the chat field, Escape stopped closing the panel. Escape is handled
  before the text-entry check.
- If loading a chat from History failed right after cancelling a reply, the busy flags were never
  cleared and the input stayed locked. Cancelling now clears them itself.
- Two sends in the same render tick could both pass the `busy` check. `send` also checks the
  in-flight request ref.

**Results:** `pytest` 72 passed, `ruff` clean, `tsc` clean.
