import { useCallback, useEffect, useRef, useState } from "react";
import { Pill } from "./components/Pill";
import { TOOLS } from "./components/tools";
import { Panel } from "./components/panels/Panel";
import { ChatPanel } from "./components/panels/ChatPanel";
import { HistoryPanel } from "./components/panels/HistoryPanel";
import { SettingsPanel } from "./components/panels/SettingsPanel";
import { ErrorPanel } from "./components/panels/ErrorPanel";
import { VoicePanel } from "./components/panels/VoicePanel";
import { RegionSelect } from "./components/RegionSelect";
import { useDrag } from "./hooks/useDrag";
import { useTheme } from "./hooks/useTheme";
import { useHealth } from "./hooks/useHealth";
import { useSettings } from "./hooks/useSettings";
import { useChat } from "./hooks/useChat";
import {
  isTauri, startDragging, fitWindowToContent, registerShortcut, watchWindowMoves,
  onToggleOverlay, onRegionCancel, captureScreen, setFullscreen,
  armRegionEscape, disarmRegionEscape,
} from "./lib/tauri";
import type { ToolId } from "./types";

const TITLES: Record<ToolId, string> = {
  chat: "Chat",
  region: "Region",
  voice: "Voice",
  history: "Past Chats",
  settings: "Settings",
};

const TAURI = isTauri();

export default function App() {
  const { theme, setTheme } = useTheme();
  const { settings, update, apiKey, setApiKey } = useSettings();
  const { model, error: healthError } = useHealth();

  const [expanded, setExpanded] = useState(false);
  const [activeTool, setActiveTool] = useState<ToolId | null>(null);
  const [hasNotif, setHasNotif] = useState(false);
  const [regionImage, setRegionImage] = useState<string | null>(null);
  const activeRef = useRef<ToolId | null>(null);
  activeRef.current = activeTool;
  const wrapRef = useRef<HTMLDivElement>(null);

  const chat = useChat(() => {
    if (activeRef.current !== "chat") setHasNotif(true);
  });
  const chatRef = useRef(chat);
  chatRef.current = chat;

  const { pos, moved, onMouseDown: jsDrag } = useDrag({
    x: window.innerWidth - 220,
    y: window.innerHeight - 80,
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
    let timer = 0;
    const fit = () => fitWindowToContent(wrap);
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
      // Coalesce rapid frames (CSS animation) into one call at the end
      timer = window.setTimeout(() => { raf = requestAnimationFrame(fit); }, 32);
    });
    wrap.querySelectorAll(".gv-pill, .gv-panel").forEach((el) => ro.observe(el));
    requestAnimationFrame(fit);
    return () => { ro.disconnect(); clearTimeout(timer); cancelAnimationFrame(raf); };
  }, [expanded, activeTool, regionImage]);

  // Rebind the global shortcut when it changes (native only).
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

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!expanded) return;
      if (e.target instanceof HTMLElement && e.target.tagName === "INPUT") return;
      if (e.key === "Escape") return setActiveTool(null);
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

  const openHistoryChat = useCallback((id: string) => {
    chatRef.current.load(id);
    setActiveTool("chat");
  }, []);

  const renderPanel = () => {
    if (!activeTool) return null;
    if (activeTool === "chat" && healthError) {
      return (
        <Panel title={TITLES.chat} onClose={closePanel}>
          <ErrorPanel onOpenSettings={() => setActiveTool("settings")} />
        </Panel>
      );
    }
    return (
      <Panel title={TITLES[activeTool]} onClose={closePanel}>
        {activeTool === "chat" && (
          <ChatPanel
            messages={chat.messages}
            thinking={chat.thinking}
            streaming={chat.streaming}
            streamText={chat.streamText}
            busy={chat.busy}
            onSend={chat.send}
          />
        )}
        {activeTool === "history" && <HistoryPanel onOpen={openHistoryChat} visible={activeTool === "history"} />}
        {activeTool === "voice" && (
          <VoicePanel
            onTranscript={(text) => {
              setActiveTool("chat");
              chat.send(text);
            }}
          />
        )}
        {activeTool === "settings" && (
          <SettingsPanel
            settings={settings}
            update={update}
            theme={theme}
            setTheme={setTheme}
            apiKey={apiKey}
            setApiKey={setApiKey}
            model={model}
          />
        )}
      </Panel>
    );
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
        {renderPanel()}
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
