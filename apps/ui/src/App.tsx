import { useCallback, useEffect, useState } from "react";
import { GlassSurface } from "./glass/GlassSurface";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { Composer } from "./components/Composer";
import { api } from "./lib/api";
import { captureFullscreen, onNative, startSnip } from "./lib/tauri";
import type { ChatSummary, Message } from "./lib/types";

export default function App() {
  const [model, setModel] = useState<string>("...");
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshChats = useCallback(() => api.listChats().then(setChats), []);

  // --- bootstrap -----------------------------------------------------------
  useEffect(() => {
    api.health().then((h) => setModel(h.model)).catch(() => setModel("offline"));
    (async () => {
      const list = await api.listChats();
      setChats(list);
      if (list.length > 0) {
        await selectChat(list[0].id);
      } else {
        await newChat();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- native events (snip + hotkey) ---------------------------------------
  useEffect(() => {
    const unsubs: Array<Promise<() => void>> = [
      onNative<string>("snip-complete", (dataUrl) => setPendingImage(dataUrl)),
      onNative("snip-cancel", () => {}),
      onNative("snip-hotkey", () => void startSnip()),
    ];
    return () => {
      unsubs.forEach((p) => p.then((un) => un()));
    };
  }, []);

  // --- chat actions --------------------------------------------------------
  async function selectChat(id: string) {
    const detail = await api.getChat(id);
    setActiveId(detail.id);
    setMessages(detail.messages);
  }

  async function newChat() {
    const chat = await api.newChat();
    setActiveId(chat.id);
    setMessages([]);
    await refreshChats();
  }

  async function deleteChat(id: string) {
    await api.deleteChat(id);
    const list = await api.listChats();
    setChats(list);
    if (id === activeId) {
      if (list.length > 0) await selectChat(list[0].id);
      else await newChat();
    }
  }

  async function send(message: string) {
    if (!activeId || busy) return;
    const image = pendingImage ?? undefined;
    setBusy(true);
    setPendingImage(null);

    setMessages((prev) => [
      ...prev,
      { role: "user", content: message, images: image ? [image] : [] },
      { role: "assistant", content: "" },
    ]);

    try {
      await api.streamChat({ chat_id: activeId, message, image }, (chunk) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + chunk };
          return next;
        });
      });
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `Error: ${String(err)}`,
        };
        return next;
      });
    } finally {
      setBusy(false);
      refreshChats();
    }
  }

  async function captureFull() {
    const dataUrl = await captureFullscreen();
    if (dataUrl) setPendingImage(dataUrl);
  }

  return (
    <div className="app">
      <Sidebar
        chats={chats}
        activeId={activeId}
        onSelect={selectChat}
        onNew={newChat}
        onDelete={deleteChat}
      />
      <GlassSurface className="app__main">
        <div className="chat">
          <div className="topbar">
            <span>GlassView</span>
            <span className="topbar__model">{model}</span>
          </div>
          <ChatView messages={messages} />
          <Composer
            pendingImage={pendingImage}
            busy={busy}
            onSend={send}
            onClearImage={() => setPendingImage(null)}
            onCaptureFull={captureFull}
            onSnip={() => void startSnip()}
          />
        </div>
      </GlassSurface>
    </div>
  );
}
