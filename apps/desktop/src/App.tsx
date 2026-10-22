import { useCallback, useEffect, useRef, useState } from "react";
import { Pill } from "./components/Pill";
import { TOOLS } from "./components/tools";
import { Panel, type PanelOrigin } from "./components/panels/Panel";
import { ChatPanel } from "./components/panels/ChatPanel";
import { HistoryPanel } from "./components/panels/HistoryPanel";
import { SettingsPanel } from "./components/panels/SettingsPanel";
import { ErrorPanel } from "./components/panels/ErrorPanel";
import { RegionSelect } from "./components/RegionSelect";
import { useDrag } from "./hooks/useDrag";
import { useTheme } from "./hooks/useTheme";
import { useHealth } from "./hooks/useHealth";
import { useSettings } from "./hooks/useSettings";
import { useChat } from "./hooks/useChat";
import {
  isTauri, startDragging, fitWindowToContent, registerShortcut, watchWindowMoves,
  onToggleOverlay, onRegionCancel, captureScreen, setFullscreen,
  armRegionEscape, disarmRegionEscape, setAutostart, isAutostartEnabled,
} from "./lib/tauri";
import type { ToolId } from "./types";

const TITLES: Record<ToolId, string> = {
  chat: "Chat",
  region: "Region",
  history: "Past Chats",
  settings: "Settings",
};

const TAURI = isTauri();

// Must match the .gv-panel.closing animation duration in global.css.
const PANEL_EXIT_MS = 160;

interface LivePanel {
  tool: ToolId;
  origin: PanelOrigin;
  closing: boolean;
}

/** True when a key press is text entry, so single-letter tool hotkeys must not fire. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

/** Fallback origin (panel's own bottom-right) if the button can't be measured. */
const FALLBACK_ORIGIN: PanelOrigin = { x: 320, dy: 30 };

export default function App() {
  const { theme, setTheme } = useTheme();
  const { settings, update, apiKey, setApiKey } = useSettings();
  const { model, error: healthError } = useHealth();

  const [expanded, setExpanded] = useState(false);
  const [activeTool, setActiveTool] = useState<ToolId | null>(null);
  // Live panels. More than one exists only mid-switch, when the outgoing panel is
  // still minimizing while the incoming one maximizes.
  const [panels, setPanels] = useState<LivePanel[]>([]);
  const [hasNotif, setHasNotif] = useState(false);
  const [regionImage, setRegionImage] = useState<string | null>(null);
  const activeRef = useRef<ToolId | null>(null);
  activeRef.current = activeTool;
  const wrapRef = useRef<HTMLDivElement>(null);

  const chat = useChat({
    streaming: settings.streaming,
    redact: settings.privacy,
    provider: settings.provider,
    apiKey: settings.provider === "ollama" ? "" : apiKey,
    onDone: () => {
      if (activeRef.current !== "chat") setHasNotif(true);
    },
  });
  const chatRef = useRef(chat);
  chatRef.current = chat;

  // Browser-only resting spot. The pill is 226px wide / 42px tall; keep a ~16px margin so
  // it never starts clipped against the right/bottom edge (Tauri pins right:0 bottom:0).
  const { pos, moved, onMouseDown: jsDrag } = useDrag({
    x: window.innerWidth - 242,
    y: window.innerHeight - 64,
  });

  useEffect(() => {
    document.body.dataset.stage = TAURI ? "tauri" : "dev";
  }, []);

  // Keep the window anchor synced to user drags.
  useEffect(() => {
    if (!TAURI) return;
    let un: (() => void) | undefined;
    watchWindowMoves().then((u) => { un = u; });
    return () => un?.();
  }, []);

  // Native window: fit to content (logo anchored) whenever the toolbar/panel open or
  // their content grows. The panel is out of flow, so re-run on expanded/activeTool and
  // observe both the pill and the panel for streaming/content growth.
  useEffect(() => {
    if (!TAURI || regionImage) return; // don't resize while fullscreen for region
    const wrap = wrapRef.current;
    if (!wrap) return;
    let raf = 0;
    const fit = () => fitWindowToContent(wrap);
    // Coalesce bursts into a single fit on the next frame — no extra timeout, so the
    // window resizes on the same frame the panel mounts (avoids a one-frame blank where
    // the toolbar flashes before the grown window catches up).
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(fit);
    });
    wrap.querySelectorAll(".gv-pill, .gv-panel").forEach((el) => ro.observe(el));
    requestAnimationFrame(fit);
    return () => { ro.disconnect(); cancelAnimationFrame(raf); };
  }, [expanded, activeTool, panels, regionImage]);

  // Launch-on-login: the OS registration is the source of truth, so adopt it on
  // startup rather than trusting the stored setting (the user may have changed it
  // elsewhere, or the registration may have failed last time).
  // `osAutoLaunch` is the value last known to be registered with the OS; null until
  // the startup read settles, so nothing is written before the OS has been asked.
  const osAutoLaunch = useRef<boolean | null>(null);
  useEffect(() => {
    if (!TAURI) return;
    const stored = settings.autoLaunch;
    isAutostartEnabled()
      .then((on) => {
        osAutoLaunch.current = on;
        update("autoLaunch", on);
      })
      .catch((err) => {
        // Unknown OS state: assume the stored value holds and write only on a change.
        osAutoLaunch.current = stored;
        console.error("[autostart] read failed:", err);
      });
    // Intentionally mount-only: this seeds the setting from the OS.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apply user changes to launch-on-login. Only writes when the setting differs from
  // what the OS already has, so seeding (and StrictMode's re-run) never re-writes it.
  useEffect(() => {
    if (!TAURI) return;
    const want = settings.autoLaunch;
    if (osAutoLaunch.current === null || osAutoLaunch.current === want) return;
    osAutoLaunch.current = want;
    setAutostart(want).catch((err) => {
      osAutoLaunch.current = !want;
      console.error("[autostart] write failed:", err);
    });
  }, [settings.autoLaunch]);

  // Bind the stored shortcut on launch (native only). Settings validates and
  // registers a new one before saving it, so a later change here is already bound
  // and the Rust side treats the repeat as a no-op.
  useEffect(() => {
    if (TAURI) {
      registerShortcut(settings.shortcut).catch((err) => {
        console.error("[shortcut] failed to register:", err);
      });
    }
  }, [settings.shortcut]);

  // Leave region mode: drop fullscreen, disarm the Esc failsafe, clear the capture.
  const exitRegion = useCallback(() => {
    setRegionImage(null);
    disarmRegionEscape().catch(() => {});
    setFullscreen(false).catch(() => {});
  }, []);
  const exitRegionRef = useRef(exitRegion);
  exitRegionRef.current = exitRegion;

  // Events from Rust: hotkey toggle + region force-cancel failsafe.
  useEffect(() => {
    const uns: Array<() => void> = [];
    onToggleOverlay(() => {
      setExpanded((e) => !e);
      setHasNotif(false);
    }).then((u) => uns.push(u));
    onRegionCancel(() => exitRegionRef.current()).then((u) => uns.push(u));
    return () => uns.forEach((u) => u());
  }, []);

  // Enter region mode: capture the screen, go fullscreen, arm the Esc failsafe, then
  // render the selector inside this (working) window.
  const startRegion = useCallback(async () => {
    if (!TAURI) return;
    try {
      const img = await captureScreen();
      if (!img) return;
      setActiveTool(null);
      setRegionImage(img);
      await setFullscreen(true);
      await armRegionEscape();
    } catch {
      exitRegionRef.current();
    }
  }, []);

  const toggleTool = useCallback(
    (id: ToolId) => {
      if (id === "region") {
        setActiveTool(null);
        startRegion();
        return;
      }
      setActiveTool((prev) => (prev === id ? null : id));
    },
    [startRegion],
  );

  const toggleExpand = useCallback(() => {
    setExpanded((e) => {
      if (e) setActiveTool(null);
      return !e;
    });
    setHasNotif(false);
  }, []);

  const onLogoClick = useCallback(() => {
    // Native: the click is decided in onDragMouseDown's mouseup (startDragging would
    // otherwise eat the click), so this is a no-op there.
    if (TAURI) return;
    if (moved.current) {
      moved.current = false;
      return;
    }
    toggleExpand();
  }, [moved, toggleExpand]);

  const onDragMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!TAURI) {
        jsDrag(e);
        return;
      }
      if (e.button !== 0) return;
      // Hand off to the OS window drag only once the press moves past a threshold;
      // a release without movement counts as a click and toggles the toolbar.
      const sx = e.clientX;
      const sy = e.clientY;
      let dragged = false;
      const cleanup = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
      };
      const move = (ev: MouseEvent) => {
        if (!dragged && (Math.abs(ev.clientX - sx) > 4 || Math.abs(ev.clientY - sy) > 4)) {
          dragged = true;
          cleanup();
          startDragging();
        }
      };
      const up = () => {
        cleanup();
        if (!dragged) toggleExpand();
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    },
    [jsDrag, toggleExpand],
  );

  const closePanel = useCallback(() => setActiveTool(null), []);

  /**
   * Where the panel should scale from: the centre of the tool button that owns it,
   * expressed relative to the panel box. The panel is absolutely positioned with
   * `right: 0; bottom: calc(100% + 10px)`, so its bottom edge sits 10px above the
   * wrapper and its left edge is `panelWidth` in from the wrapper's right edge.
   */
  const originFor = useCallback((tool: ToolId): PanelOrigin => {
    const wrap = wrapRef.current;
    const btn = wrap?.querySelector<HTMLElement>(`[data-tool="${tool}"]`);
    if (!wrap || !btn) return FALLBACK_ORIGIN;
    const w = wrap.getBoundingClientRect();
    const b = btn.getBoundingClientRect();
    const panelW = wrap.querySelector<HTMLElement>(".gv-panel")?.offsetWidth ?? 340;
    return {
      x: b.left + b.width / 2 - (w.right - panelW),
      dy: b.top + b.height / 2 - (w.top - 10),
    };
  }, []);

  useEffect(() => {
    setPanels((prev) => {
      const closing = prev.map((p) => ({ ...p, closing: true }));
      if (!activeTool) return closing;
      // Drop any stale copy of the incoming tool so it remounts and replays its
      // maximize animation rather than being reconciled in place.
      return [
        ...closing.filter((p) => p.tool !== activeTool),
        { tool: activeTool, origin: originFor(activeTool), closing: false },
      ];
    });
  }, [activeTool, originFor]);

  // Retire panels once they have finished minimizing.
  useEffect(() => {
    if (!panels.some((p) => p.closing)) return;
    const t = setTimeout(
      () => setPanels((ps) => ps.filter((p) => !p.closing)),
      PANEL_EXIT_MS,
    );
    return () => clearTimeout(t);
  }, [panels]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!expanded) return;
      // Escape closes the panel even from the chat field, which now keeps focus.
      if (e.key === "Escape") return setActiveTool(null);
      if (isTypingTarget(e.target)) return;
      // Ctrl+C (copy), Alt+S, etc. belong to the OS/webview, not the tool hotkeys.
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tool = TOOLS.find((t) => t.kbd === e.key.toUpperCase());
      if (tool) {
        e.preventDefault();
        toggleTool(tool.id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [expanded, toggleTool]);

  useEffect(() => {
    if (!activeTool || !settings.closeOnBlur) return;
    const handler = (e: MouseEvent) => {
      if (e.target instanceof HTMLElement && !e.target.closest(".gv-wrap")) {
        setActiveTool(null);
      }
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [activeTool, settings.closeOnBlur]);

  // Region Esc (webview-side; the Rust global Esc is the failsafe if this is frozen).
  useEffect(() => {
    if (!regionImage) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") exitRegion();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [regionImage, exitRegion]);

  const onRegionDone = useCallback((cropped: string) => {
    exitRegion();
    setExpanded(true);
    setActiveTool("chat");
    chatRef.current.send("What's in this region?", cropped);
  }, [exitRegion]);

  const onChatDeleted = useCallback((id: string) => {
    // If the deleted chat is the one loaded in the Chat panel, clear it so the
    // panel isn't showing a transcript the backend no longer has.
    if (chatRef.current.chatId === id) chatRef.current.reset();
  }, []);

  const openHistoryChat = useCallback((id: string) => {
    chatRef.current.load(id);
    setActiveTool("chat");
  }, []);

  const panelBody = (tool: ToolId) => {
    // The Ollama health check only gates chat when Ollama is the provider —
    // a cloud key answers fine with the local daemon stopped.
    if (tool === "chat" && healthError && settings.provider === "ollama") {
      return <ErrorPanel onOpenSettings={() => setActiveTool("settings")} />;
    }
    if (tool === "chat") {
      return (
        <ChatPanel
          messages={chat.messages}
          thinking={chat.thinking}
          streaming={chat.streaming}
          streamText={chat.streamText}
          busy={chat.busy}
          onSend={chat.send}
        />
      );
    }
    if (tool === "history") {
      return (
        <HistoryPanel
          onOpen={openHistoryChat}
          onDeleted={onChatDeleted}
          visible={activeTool === "history"}
        />
      );
    }
    if (tool === "settings") {
      return (
        <SettingsPanel
          settings={settings}
          update={update}
          theme={theme}
          setTheme={setTheme}
          apiKey={apiKey}
          setApiKey={setApiKey}
          model={model}
        />
      );
    }
    return null;
  };

  // Browser: float at the JS-drag position. Native: pin bottom-right of the fitted window.
  const wrapStyle: React.CSSProperties = TAURI
    ? { position: "fixed", right: 0, bottom: 0 }
    : { position: "fixed", left: pos.x, top: pos.y };

  return (
    <>
      {regionImage && (
        <RegionSelect image={regionImage} onDone={onRegionDone} onCancel={exitRegion} />
      )}
      <div className="gv-wrap" ref={wrapRef} style={wrapStyle}>
        {panels.map((p) => (
          <Panel
            key={p.tool}
            title={TITLES[p.tool]}
            onClose={closePanel}
            origin={p.origin}
            closing={p.closing}
          >
            {panelBody(p.tool)}
          </Panel>
        ))}
        <Pill
          expanded={expanded}
          activeTool={activeTool}
          hasNotif={hasNotif}
          onLogoClick={onLogoClick}
          onToggleTool={toggleTool}
          onDragMouseDown={onDragMouseDown}
        />
      </div>
    </>
  );
}
