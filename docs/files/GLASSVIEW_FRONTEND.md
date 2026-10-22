# GlassView — Frontend Build Brief

## Context

GlassView is a local-first desktop AI overlay. The backend already exists: a FastAPI +
Ollama service (`glassview_ai/`) exposing a small HTTP API (see `README.md`). This
document covers the frontend only — a Tauri v2 + React + TypeScript app that wraps that
backend.

---

## What we're building

A minimal always-on-top desktop overlay that lives in the background and surfaces
instantly when the user needs it. Think Alfred/Spotlight meets an AI assistant — but
visual, context-aware, and non-intrusive.

### Core interaction model

1. App launches → small pill with a two-tone G logo sits in the bottom-right corner
2. User presses **Ctrl+Shift+Space** (configurable) → pill expands into a toolbar
3. User picks a tool → panel opens anchored directly above the pill
4. Panel closes → toolbar collapses back to pill

The pill is **draggable** to anywhere on screen. The panel always opens relative to
wherever the pill currently is.

---

## Tech stack

- **Tauri v2** — native shell (window management, global shortcuts, tray, permissions)
- **React 18 + TypeScript** — UI
- **Vite** — build tool
- **No UI library** — custom CSS only, system font stack
- **No state management library** — React state is sufficient

### Tauri plugins needed

```toml
tauri-plugin-global-shortcut = "2"
tauri-plugin-autostart       = "2"
tauri-plugin-shell           = "2"
```

Screen capture is handled by passing a base64 screenshot from the frontend to the
backend — use the Tauri `@tauri-apps/plugin-screenshot` or fall back to
`html2canvas` for the prototype. macOS will need the screen recording permission
prompt wired up.

---

## Window configuration (`tauri.conf.json`)

```json
{
  "app": {
    "windows": [{
      "label": "main",
      "title": "GlassView",
      "width": 1,
      "height": 1,
      "transparent": true,
      "decorations": false,
      "alwaysOnTop": true,
      "skipTaskbar": true,
      "resizable": false,
      "fullscreen": false,
      "visible": true
    }]
  }
}
```

The window covers the full screen (set via Rust at startup using
`window.set_size(PhysicalSize::new(screen_w, screen_h))`). The UI itself is small —
the window is just a transparent canvas the overlay sits on.

---

## Project structure

```
glassview/
  src-tauri/
    src/
      main.rs          Entry point, window setup, global shortcut, tray
      lib.rs           Tauri commands (screen capture, permission check)
    tauri.conf.json
    Cargo.toml
  src/
    main.tsx           React entry
    App.tsx            Root — theme provider, toolbar + panel router
    components/
      Pill.tsx         Draggable pill with G logo, expand/collapse, notif pulse
      Toolbar.tsx      Expanded tool icon strip
      panels/
        ChatPanel.tsx  Chat UI — context strip, file attach, messages, input
        VoicePanel.tsx Mic button, recording state, transcript
        HistoryPanel.tsx Searchable past chats list
        SettingsPanel.tsx All settings (theme, API key, shortcut, toggles)
        ErrorPanel.tsx  Ollama not running / no model fallback
    hooks/
      useStream.ts     Fetch streaming response from /chat, yield tokens
      useDrag.ts       Draggable position logic (used by Pill)
      useTheme.ts      Dark/light theme, persisted to localStorage
      useSettings.ts   Settings state, persisted to localStorage
    api/
      client.ts        Typed wrappers for all backend endpoints
    styles/
      tokens.ts        Theme token objects (dark + light)
      global.css       Reset + base styles
    types.ts           Shared TypeScript types
```

---

## Design system

### Theme tokens — dark (default)

```ts
const dark = {
  bg:             "#0d0d0d",
  pillBg:         "rgba(20,20,22,.88)",
  pillBorder:     "rgba(255,255,255,.11)",
  panelBg:        "rgba(18,18,20,.92)",
  panelBorder:    "rgba(255,255,255,.09)",
  inputBg:        "rgba(255,255,255,.06)",
  inputBorder:    "rgba(255,255,255,.09)",
  inputFocus:     "rgba(10,132,255,.4)",
  bubbleUserBg:   "#0A84FF",
  bubbleAiBg:     "rgba(255,255,255,.07)",
  bubbleAiBorder: "rgba(255,255,255,.08)",
  textPrimary:    "rgba(255,255,255,.85)",
  textSecondary:  "rgba(255,255,255,.4)",
  textFaint:      "rgba(255,255,255,.2)",
  sepColor:       "rgba(255,255,255,.09)",
  accent:         "#0A84FF",
  errorBg:        "rgba(255,69,58,.08)",
  errorBorder:    "rgba(255,69,58,.2)",
  errorText:      "rgba(255,69,58,.9)",
}
```

### Theme tokens — light

```ts
const light = {
  bg:             "#e8e8ed",
  pillBg:         "rgba(255,255,255,.82)",
  pillBorder:     "rgba(0,0,0,.1)",
  panelBg:        "rgba(255,255,255,.92)",
  panelBorder:    "rgba(0,0,0,.08)",
  inputBg:        "rgba(0,0,0,.04)",
  inputBorder:    "rgba(0,0,0,.08)",
  inputFocus:     "rgba(10,132,255,.4)",
  bubbleUserBg:   "#0A84FF",
  bubbleAiBg:     "rgba(0,0,0,.04)",
  bubbleAiBorder: "rgba(0,0,0,.06)",
  textPrimary:    "rgba(0,0,0,.82)",
  textSecondary:  "rgba(0,0,0,.4)",
  textFaint:      "rgba(0,0,0,.22)",
  sepColor:       "rgba(0,0,0,.08)",
  accent:         "#0A84FF",
  errorBg:        "rgba(255,69,58,.06)",
  errorBorder:    "rgba(255,69,58,.18)",
  errorText:      "rgba(200,40,30,.9)",
}
```

### Typography

System UI stack only — no external fonts for now:
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
```

### Logo — two-tone split G

SVG rendered inline. The G is a ~320° arc with a horizontal crossbar arm. A ghost copy
is offset by `(dx, dy)` behind the primary. The primary G is split horizontally at
`cy + 4%` — top half `#0A84FF`, bottom half `rgba(255,255,255,0.88)`. Ghost is
`rgba(255,255,255,0.13)`.

```tsx
// GLogo.tsx — sizes: 22px (pill), 16px (tray)
function GLogo({ size, pulse = false }) {
  const c = size / 2, r = size * 0.315, sw = size * 0.072
  const openAngle = -0.22, sweep = 1.78 * Math.PI
  // ... build arc path, ghost path, clip top/bottom halves
  // pulse = true → animated ring SVG element for notif state
}
```

When `pulse=true` (response arrived while collapsed), add an SVG `<circle>` with
`animate` elements expanding outward and fading.

---

## UI states

### 1. Collapsed (idle)
- Pill visible, logo centered, no tools shown
- If `hasNotif=true`, logo pulses (animated SVG ring)

### 2. Toolbar expanded
- Pill expands right to reveal 5 tool icon buttons
- Smooth width transition: `max-width: 0 → 240px`, `opacity: 0 → 1`
- Each icon has a tooltip on hover showing label + kbd shortcut

### 3. Panel open (anchored above pill)
- Panel `transform-origin: bottom center`, animates in with
  `scale(0.92) translateY(6px) → scale(1) translateY(0)`
- Always positioned `bottom: calc(100% + 10px)` relative to pill wrapper
- Panel width: `340px`
- Backdrop filter: `blur(48px) saturate(200%)`

### 4. Error state (no model)
- Shown instead of chat content when `/health` returns no model or Ollama unreachable
- Red-tinted panel with warning icon, description, "Open Settings" button

### 5. Notif (response while collapsed)
- `hasNotif` flag set when stream completes and panel is not open
- Logo animates until user opens the toolbar

---

## Tools

### Chat (`C`)
Panel sections top to bottom:
1. **Context strip** — thumbnail of active window, app name, "VS Code · active window"
2. **File attach zone** — dashed border, drag-and-drop or click. Shows chip when file attached
3. **Message list** — scrollable, max-height `190px`, user bubbles right / AI bubbles left
4. **Thinking state** — three bouncing dots in AI bubble
5. **Streaming** — text appears token by token with blinking cursor
6. **Input row** — attach icon button + text input + send button

### Region select (`R`)
- No panel — triggers a full-screen transparent overlay
- Dark tint (`rgba(0,0,0,0.48)`) with crosshair cursor
- User drags to select a region → selection box with blue border
- On mouseup: capture region, dismiss overlay, open Chat panel with region as context
- Cancel button at bottom center

### Voice (`V`)
- Mic button centered in panel
- `recording=false`: static mic icon, "Tap to speak" label
- `recording=true`: three animated pulsing rings, mic turns red, "Listening…"
- On stop: transcript appears, auto-sends to Chat

### Past Chats (`H`)
- Search input at top (filters by title + preview)
- List of chat items: title, relative timestamp, preview snippet
- Click → opens Chat panel with that history loaded
- Data from `GET /chats` + `GET /chats/{id}`

### Settings (`S`)
Sections:

**Appearance**
- Theme toggle: Dark / Light buttons

**Model**
- API key input (password field)
- Auto-detect provider from key prefix:
  - no key → Ollama (badge: green "Ollama")
  - `sk-` → OpenAI (badge: blue "OpenAI")
  - `sk-ant-` → Anthropic (badge: amber "Anthropic")
- If Ollama: show detected model name (from `/health`)

**Shortcut**
- Text input pre-filled with `Ctrl+Shift+Space`
- On change: call Tauri `register_shortcut` command to rebind

**Behavior**
- Close on click outside (toggle) — default: on
- Auto-launch on login (toggle) — default: off
- Stream responses (toggle) — default: on

**Privacy**
- Privacy redaction (toggle) — default: on
- Auto-capture context (toggle) — default: on

All settings persisted to `localStorage`. On load, read and apply.

---

## Backend API integration

Base URL: `http://127.0.0.1:8765`. All calls via `fetch`.

```ts
// api/client.ts

export const api = {
  health: () => fetch('/health').then(r => r.json()),

  listChats: () => fetch('/chats').then(r => r.json()),

  getChat: (id: string) => fetch(`/chats/${id}`).then(r => r.json()),

  createChat: (title?: string) =>
    fetch('/chats', { method: 'POST', body: JSON.stringify({ title }) }).then(r => r.json()),

  // Streaming — yields string chunks
  chat: async function* (chatId: string, message: string, image?: string) {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, message, image }),
    })
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      yield decoder.decode(value)
    }
  },

  recall: (q: string, k = 5) =>
    fetch(`/recall?q=${encodeURIComponent(q)}&k=${k}`).then(r => r.json()),
}
```

Image input: base64 string or data URL. Pass from region capture or file attach.

On app start: call `/health`. If it throws or returns no model → set `ollamaError=true`.
Poll every 10s while in error state, clear flag when resolved.

---

## Rust / Tauri side (`main.rs`)

```rust
// Key setup tasks:

// 1. Fullscreen transparent window
window.set_size(PhysicalSize::new(screen_width, screen_height))?;
window.set_always_on_top(true)?;
window.set_decorations(false)?;

// 2. Global shortcut (default Ctrl+Shift+Space)
app.global_shortcut().on_shortcut("Ctrl+Shift+Space", |_app, _shortcut, _event| {
    // emit event to frontend
    app.emit("toggle-overlay", ()).unwrap();
});

// 3. System tray
let tray = TrayIconBuilder::new()
    .icon(app.default_window_icon().unwrap().clone())
    .menu(&menu)
    .build(app)?;

// 4. macOS screen capture permission
// Check and prompt via tauri-plugin-macos-permissions or native API
```

Expose a `get_screen_capture` Tauri command that:
1. Checks permission on macOS, prompts if needed
2. Captures the full screen or a region
3. Returns base64 PNG

---

## Build order

Build in this sequence — each step is independently testable:

1. **Tauri scaffold** — `create-tauri-app`, configure transparent fullscreen window,
   confirm it renders correctly on both platforms

2. **Pill + drag** — render the G logo pill at bottom-right, implement drag with
   `useDrag`, confirm position persists across expand/collapse

3. **Toolbar expand** — add tool buttons, wire expand/collapse to logo click and
   global shortcut event from Tauri

4. **Theme system** — implement `useTheme`, inject CSS variables, wire theme toggle
   in settings

5. **Chat panel** — wire to `/chat` streaming endpoint using `useStream`, implement
   message list, input, context strip

6. **History panel** — wire to `GET /chats`, implement search filter

7. **Settings panel** — all toggles, API key detection, shortcut rebinding via Tauri
   command, persist to localStorage

8. **Error state** — health check on startup + polling, show `ErrorPanel` when needed

9. **Region select** — fullscreen overlay, drag selection, capture + send to chat

10. **Voice** — mic input, Web Speech API or Whisper via backend

11. **File attach** — drag-and-drop, base64 encode, pass as `image` field to `/chat`

12. **Tray icon** — system tray with show/hide/quit menu

13. **Notifications** — `hasNotif` pulse when response arrives while collapsed

14. **Polish** — spring animations on panel, message entrance, toggle micro-interactions

---

## Key constraints

- Panel always opens **above** the pill, never below or to the side
- Toolbar expands **horizontally** from the pill, not vertically
- No edge snapping — pill floats freely wherever dropped
- Multi-monitor: always on primary monitor
- Click-outside-to-dismiss is **user-configurable** (settings toggle), not hardcoded
- Global shortcut **Ctrl+Shift+Space** default, must work on both Windows and macOS
- Light/dark theme applies to **all** UI including pill, toolbar, and panel
- Font: system UI stack only for now

---

## Reference mockup

The full interactive mockup is in `glassview-mockup.jsx` — a self-contained React
artifact showing all states, both themes, all panels, drag behavior, streaming, error
state, and notifications. Use it as the visual reference for every component.
