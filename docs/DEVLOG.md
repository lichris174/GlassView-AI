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

---

## 2026-10-14 — Phase 1: data pipeline

Built the tooling for collecting and splitting the dataset before collecting any data, so the rules
that make the numbers honest are enforced by code rather than remembered.

### Capture (`ml/capture.py`)
- Grabs the primary monitor every few seconds during a named session.
- **Skips near-duplicates** using a 64-bit difference hash (dHash): a tiny grayscale thumbnail
  where each bit records whether a pixel is brighter than its neighbour. A blinking cursor flips a
  few bits; a new screen flips many. Frames under 6 bits from the last saved one are dropped, so
  idle time does not flood the dataset with copies that would make it look bigger than it is.
- Records the foreground app and window title per frame (Windows API via `ctypes`, no extra
  dependency), for summarizing the dataset by app later.
- **Saves outside the repo and outside OneDrive** (`%LOCALAPPDATA%\GlassView\dataset`). Even fake
  sensitive data should not be synced or committable by accident.

### Splits (`ml/splits.py`)
- **Splits by session, not by frame.** Frames within a session are near-copies. A per-frame random
  split would put almost-identical screens in train and test, and test scores would measure
  memorization instead of generalization. This is the single most common way small vision datasets
  overstate results.
- **Freezes the test set.** `splits.json` stores a SHA-256 of every test frame plus one hash over
  the whole set. New sessions captured later go to train only. `make verify-split` fails if any
  test frame is added, removed, or edited.
- Deterministic (fixed seed) and refuses to freeze with fewer than 5 sessions.

### Labeling guide (`docs/LABELING_GUIDE.md`)
Five classes (`credential`, `api_key`, `financial`, `private_message`, `personal_id`), with what to
box and what not to box for each, edge cases decided once (masked values *are* boxed; unreadable
text is not), a collection plan by session theme, and a target of ~300 frames from 15+ sessions with
about a third containing nothing sensitive. Those empty frames are how the false-blur rate gets
measured.

**Verified:** 81 tests pass (9 new: hashing, session validation, split determinism, sessions never
straddling splits, frozen test set, tamper detection). Smoke-tested both CLIs on a real 2560×1600
capture, then deleted the frames.

**Next (manual):** capture sessions per the collection plan, review, freeze the split, label.

---

## 2026-10-15 — Phase 2: eval harness and baselines

### What gets measured, and why these metrics
The app blurs every predicted box regardless of its class, so the headline metrics are
**class-agnostic on the prediction side** (`ml/metrics.py`):

| Metric | Meaning | Why |
|---|---|---|
| Region recall | Share of labeled regions at least 90% covered by blur | The safety number: did the secret leak? |
| Pixel recall | Share of sensitive pixels blurred | Partial credit view of the same |
| Blur precision | Share of blurred pixels that were sensitive | Over-blurring costs answer quality |
| Clean-frame false-blur rate | Share of harmless frames that get anything blurred | Cost in block mode; measured on the ~1/3 empty frames |
| Sensitive-frame recall | Share of sensitive frames with any box | The block-mode safety number |
| AP@0.5 per class, mAP@0.5 | Standard detection metric (PASCAL VOC) | What ML readers expect to compare |

"90% covered" is a parameter recorded in every run. A secret 90% blurred can still leak its edges,
so results can be rescored at stricter coverage without rerunning a model.

### Making the numbers defensible
- **Session-cluster bootstrap.** Confidence intervals resample whole capture sessions, not frames.
  Frames in a session are near-copies; treating them as independent evidence would make intervals
  look tighter than the data supports.
- **Paired comparisons.** `ml.evaluate compare` resamples the *same* sessions for both systems, so
  "detector beats OCR by N points" comes with an interval on the difference itself.
- **Threshold chosen on val, never test.** `--threshold-from <val run> --target-recall 0.95` records
  where the threshold came from in the manifest; `pick-threshold` refuses a test run.
- **Run folders** (`results/<stamp>-<system>-<split>/`): manifest with git commit + dirty flag, the
  frozen split hash, a hash of the labels, system config (e.g. Ollama model *digest*, not just the
  tag, and a prompt hash), machine and GPU; full predictions; metrics with intervals. Rescoring
  flags labels edited after the run.

### Baselines (`ml/baselines/`)
- `block_all`: blur everything. Recall 100% and false-blur 100% by construction; the floor.
- `ocr_regex`: Tesseract word boxes + the app's existing redaction rules, i.e. what GlassView does
  today. Run with default Tesseract settings, untuned, to represent what ships. Cannot see faces,
  and has no rule for private messages, so those classes score 0 by design.
- `qwen_vl`: qwen3-vl 8B via Ollama, zero-shot, temperature 0, given the same class definitions as
  the labeling guide, answering JSON boxes on Qwen3-VL's 0-1000 coordinate grid. It gives no
  confidence scores, so its AP is a single operating point; the privacy metrics are the fair
  comparison.

### Review
A Sonnet reviewer read the harness cold and confirmed the geometry, ratios, and bootstrap. Fixed
from its findings, each with a regression test:
- **AP was computed on threshold-filtered predictions**, which truncates the precision-recall curve
  and understates mAP. AP now uses all predictions; only privacy metrics use the threshold.
- **Scores were rounded to 2 decimals** in saved predictions, creating ties that shift AP and the
  picked threshold. Scores are now stored at full precision.
- **Tied scores made AP depend on frame order** for constant-score baselines. PR points are now
  emitted only between distinct scores.
- Matching switched to strict VOC (a prediction whose best-overlap ground truth is taken is a false
  positive); the previous greedy match was slightly generous.
- `choose_threshold` now reports when the target recall is unreachable instead of silently
  returning the lowest threshold.
- Labels are hashed into the manifest; `compare` refuses runs from different splits; frames
  labeled after a partial run are skipped and counted instead of crashing.
- The Qwen reply parser salvages complete boxes from replies cut off by the token limit and counts
  unparseable replies in the manifest, so lost recall from formatting is visible.
- Label import writes an empty label for exported images with no boxes, so clean frames are not
  mistaken for unlabeled ones (which would shrink the false-blur denominator).

The reviewer also noted that with ~10 test sessions, percentile intervals are approximate. Runs
report `num_sessions` next to every interval.

### Status
103 tests pass. The qwen baseline was verified up to the model call (model digest and config
resolved); the live call failed with Ollama's "model requires more system memory (3.2 GiB) than is
available (2.6 GiB)". That is free RAM at the time, not a code problem: close memory-heavy apps
before running `make baselines`. Grounding DINO / OWLv2 is deferred to Phase 3, which sets up the
PyTorch environment anyway.
