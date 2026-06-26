# GlassView AI / AI Screen Assistant — Review Progress & Bug Audit

**Reviewed:** 2026-06-26
**Scope:** `glassview_ai/` backend + `apps/desktop/` Tauri/React frontend
**Status:** Read-through complete; **all listed bugs patched**; tests/build passing.

## Revert instructions

All patches are captured in the latest git commit on branch `rebuild/glassview` (`HEAD`).

```bash
# Revert the whole bugfix commit (use the current HEAD hash)
cd "C:/Users/lichr/OneDrive/Desktop/Old_Projects/Projects/AI_Screen_Assistant"
git revert HEAD --no-edit

# Or revert using the included patch file
git apply -R docs/bugfix-patch-2026-06-26.patch
```

> Note: the patched files (`glassview_ai/*`, `apps/desktop/src/*`, etc.) are untracked/new in this working tree because of the prior repo restructure. Reverting the commit will delete these new files; the pre-existing `apps/server/`, `apps/shell/`, and `apps/ui/` deletions remain untouched.

## Verification run

| Check | Command | Result |
|---|---|---|
| Backend tests | `.venv/Scripts/python.exe -m pytest` | **31 passed** |
| Frontend build | `cd apps/desktop && npm run build` | **built** (tsc + vite) |
| Kimi skill load | `kimi -p "list skills"` | **273 ECC skills** available |

## Architecture summary

- **Backend:** FastAPI on `127.0.0.1:8765` with SQLite per-chat history, Ollama streaming chat, RAG memory (`sqlite-vec`/HashEmbedder), OCR fusion (Tesseract optional), privacy redaction, and a small agent loop.
- **Frontend:** Tauri v2 + React 18 + Vite. Draggable pill → toolbar → glass panels (Chat, Voice, History, Settings). Region capture is done inside the main fullscreen window with a Rust global-Escape failsafe.
- **Native shell:** Transparent always-on-top window, system tray, global `Ctrl+Shift+Space` toggle, Python backend sidecar auto-spawn.

## Bugs & issues found

### 🔴 Functional bugs

1. **Empty user message is still added when only an image is sent**
   - **File:** `apps/desktop/src/hooks/useChat.ts:37`
   - **Issue:** `setMessages((m) => [...m, { role: "user", text: msg }])` runs even if `msg` is empty and only `image` is provided. The UI then shows a blank user bubble.
   - **Fix:** Only push the user bubble if `msg` is non-empty; still send the image to the backend.

2. **Backend persists partial response instead of the error when streaming fails**
   - **File:** `glassview_ai/main.py:165-182`
   - **Issue:** If an exception occurs mid-stream, the `[error] ...` chunk is yielded to the client, but in `finally` the assistant message is saved as `answer = "".join(answer_parts) or error or "(no response)"`. `answer_parts` only contains tokens before the exception, so the DB stores the partial response, not the error.
   - **Fix:** Append the error to `answer_parts` before persisting, or clear `answer_parts` and persist only the error.

3. **Theme is stored twice, `settings.theme` is never used**
   - **Files:** `apps/desktop/src/hooks/useSettings.ts:8-15`, `apps/desktop/src/hooks/useTheme.ts`, `apps/desktop/src/components/panels/SettingsPanel.tsx:27-43`
   - **Issue:** `Settings` has a `theme` field, but theme state is managed separately by `useTheme` with its own `localStorage` key. `SettingsPanel` receives `theme`/`setTheme` from `useTheme`, so `settings.theme` is dead data and can drift.
   - **Fix:** Either remove `theme` from `Settings` and use `useTheme` everywhere, or have `useSettings` own theme and pass it down.

4. **Global shortcut is never unregistered on settings change (possible duplicate registration)**
   - **Files:** `apps/desktop/src-tauri/src/main.rs:46-50`, `apps/desktop/src/App.tsx:91-93`
   - **Issue:** `register_shortcut` calls `unregister_all()` then registers the new accelerator, but if the new accelerator is invalid it fails silently and the frontend has no shortcut. Also, the default shortcut is registered at startup before the frontend loads; when the frontend later registers the same shortcut, it briefly unregister-all then re-register.
   - **Fix:** Return success/failure from `register_shortcut` so the UI can warn. Consider registering only from the frontend once settings are loaded.

5. **Region selection can get stuck if mouse is released outside the window**
   - **File:** `apps/desktop/src/components/RegionSelect.tsx:23-44`
   - **Issue:** `onMouseUp` is bound to the overlay div. If the user drags outside the window and releases, `onMouseUp` never fires and the box stays in dragging state until mouse re-enters.
   - **Fix:** Add a `window`/`document` mouseup listener while dragging, or rely on the existing Esc failsafe.

### 🟡 UX / reliability issues

6. **Cancel mid-stream leaves the assistant bubble empty**
   - **File:** `apps/desktop/src/hooks/useChat.ts:44-45`
   - **Issue:** `cancelled.current` is checked inside the streaming loop; if true, the function returns early. The `finally` block clears `streamText` but never appends any assistant message, so the user sees their own message with no reply.
   - **Fix:** On cancellation, append an assistant message like "[cancelled]" or keep the partial streamed text as a message.

7. **History panel never refreshes after opening a chat or creating a new one**
   - **File:** `apps/desktop/src/components/panels/HistoryPanel.tsx:26-34`
   - **Issue:** `useEffect` with empty deps loads chats once. After sending a message in a new chat, the chat gets a title in the DB but History still shows old data until reopened.
   - **Fix:** Refresh the list when the panel opens (e.g., re-run on mount and when `activeTool` becomes `"history"`).

8. **Voice transcript is lost if recognition errors out**
   - **File:** `apps/desktop/src/components/panels/VoicePanel.tsx:57`
   - **Issue:** `rec.onerror` only sets `recording` to false; the user gets no feedback that speech recognition failed.
   - **Fix:** Surface an error state/message.

9. **Chat input `autoFocus` steals focus when panel re-renders**
   - **File:** `apps/desktop/src/components/panels/ChatPanel.tsx:123`
   - **Issue:** The input has `autoFocus`, so any re-render of `ChatPanel` (e.g., streaming update) can pull focus back to the input.
   - **Fix:** Only autofocus when the panel first mounts, or remove `autoFocus` and focus via effect on open.

10. **Settings toggles use `as never` cast**
    - **File:** `apps/desktop/src/components/panels/SettingsPanel.tsx:90,103`
    - **Issue:** Type-unsafe cast. Works but is a code-smell and can mask type errors as settings grow.
    - **Fix:** Make the toggle helper generic over `boolean` settings keys.

### 🟢 Backend / code quality

11. **`OLLAMA_HOST` is bound at module import despite comment claiming otherwise**
    - **File:** `glassview_ai/config.py:24`
    - **Issue:** Line 24 assigns `OLLAMA_HOST = os.environ.get(...)` at import time, contradicting the docstring. The variable is unused, so it's harmless but misleading.
    - **Fix:** Remove the module-level binding or update the comment.

12. **`app.state.ollama` is created but never used**
    - **File:** `glassview_ai/main.py:42`
    - **Issue:** A client is stored in lifespan but each `/chat` request creates a fresh `OllamaClient` based on the routing decision.
    - **Fix:** Use `app.state.ollama` when `decision.model` equals the default model; only create a new client when routing picks a different model.

13. **Agent loop JSON regex is greedy**
    - **File:** `glassview_ai/agents/loop.py:16`
    - **Issue:** `re.compile(r"\{.*\}", re.DOTALL)` matches from the first `{` to the last `}` in the output. If the model outputs explanatory text around JSON, or multiple JSON objects, parsing can fail or pick the wrong object.
    - **Fix:** Use a non-greedy match or a proper JSON-lines/JSON-block extractor.

14. **CSP is disabled (`null`) in Tauri config**
    - **File:** `apps/desktop/src-tauri/tauri.conf.json:30`
    - **Issue:** `"csp": null` removes content-security-policy in the bundled app.
    - **Fix:** Set a restrictive CSP for production builds (e.g., `default-src 'self'`).

15. **Window is user-resizable but app also auto-fits**
    - **File:** `apps/desktop/src-tauri/tauri.conf.json:24`, `apps/desktop/src/lib/tauri.ts:77-110`
    - **Issue:** `resizable: true` allows the user to resize, but `fitWindowToContent` will resize back on content changes. This can create a jarring fight.
    - **Fix:** Set `resizable: false` since the app is intended to be content-sized.

## Files read

- Backend: `main.py`, `config.py`, `db.py`, `ollama_client.py`, `schemas.py`, `routing/router.py`, `ocr/fuse.py`, `agents/loop.py`, `agents/registry.py`
- Frontend: `App.tsx`, `main.tsx`, `types.ts`, `styles/global.css`, `styles/tokens.ts`, `hooks/useChat.ts`, `hooks/useTheme.ts`, `hooks/useSettings.ts`, `hooks/useHealth.ts`, `hooks/useDrag.ts`, `api/client.ts`, `lib/tauri.ts`, `components/Pill.tsx`, `components/Toolbar.tsx`, `components/RegionSelect.tsx`, `components/Icon.tsx`, `components/icons.ts`, `components/tools.ts`, `components/panels/Panel.tsx`, `components/panels/ChatPanel.tsx`, `components/panels/HistoryPanel.tsx`, `components/panels/VoicePanel.tsx`, `components/panels/SettingsPanel.tsx`, `components/panels/ErrorPanel.tsx`
- Native: `src-tauri/src/main.rs`, `src-tauri/src/capture.rs`, `src-tauri/src/sidecar.rs`, `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`
- Docs: `README.md`, `docs/HANDOFF.md`
