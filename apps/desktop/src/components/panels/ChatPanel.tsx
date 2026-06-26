import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { Icons } from "../icons";
import type { Message } from "../../types";

interface ChatPanelProps {
  messages: Message[];
  thinking: boolean;
  streaming: boolean;
  streamText: string;
  busy: boolean;
  onSend: (text: string, image?: string) => void;
}

/** Read a File as a data URL (base64) for the /chat image field. */
function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export function ChatPanel({ messages, thinking, streaming, streamText, busy, onSend }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [attached, setAttached] = useState<{ name: string; dataUrl: string } | null>(null);
  const [dropOver, setDropOver] = useState(false);
  const msgsRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (msgsRef.current) msgsRef.current.scrollTop = msgsRef.current.scrollHeight;
  }, [messages, streamText, thinking]);

  // Focus the input once when the panel opens, without autoFocus stealing focus
  // on every parent re-render during streaming.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const attach = async (file: File | undefined) => {
    if (!file) return;
    setAttached({ name: file.name, dataUrl: await readAsDataUrl(file) });
  };

  const send = () => {
    if ((!input.trim() && !attached) || busy) return;
    onSend(input, attached?.dataUrl);
    setInput("");
    setAttached(null);
  };

  const hasThread = messages.length > 0 || thinking || streaming;

  return (
    <>
      {/* Context strip — placeholder until live window-context capture lands. */}
      <div className="gv-ctx">
        <div className="gv-ctx-thumb">
          {[90, 70, 85, 60, 75].map((w, i) => (
            <div key={i} className="gv-ctx-line" style={{ width: `${w}%` }} />
          ))}
        </div>
        <div className="gv-ctx-meta">
          <div className="gv-ctx-app">No context captured</div>
          <div className="gv-ctx-sub">Attach a file or use Region</div>
        </div>
      </div>

      {/* File drop / attach */}
      <div
        className={`gv-drop${dropOver ? " over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDropOver(true); }}
        onDragLeave={() => setDropOver(false)}
        onDrop={(e) => { e.preventDefault(); setDropOver(false); attach(e.dataTransfer.files?.[0]); }}
        onClick={() => fileRef.current?.click()}
      >
        <Icon d={Icons.attach} size={13} stroke={attached ? "#3BAAFF" : "var(--gv-textFaint)"} sw={1.4} />
        {attached ? (
          <div className="gv-file-chip">
            {attached.name}
            <button className="gv-file-rm" onClick={(e) => { e.stopPropagation(); setAttached(null); }}>✕</button>
          </div>
        ) : (
          <span className="gv-drop-label">Drop a file or <span>click to attach</span></span>
        )}
        <input
          ref={fileRef}
          type="file"
          hidden
          onChange={(e) => attach(e.target.files?.[0] ?? undefined)}
        />
      </div>

      {hasThread && (
        <div className="gv-msgs" ref={msgsRef}>
          {messages.map((m, i) => (
            <div key={i} className={`gv-msg gv-msg-${m.role === "user" ? "u" : "a"}`}>
              <div className={`gv-bubble gv-bubble-${m.role === "user" ? "u" : "a"}`}>{m.text}</div>
            </div>
          ))}
          {thinking && (
            <div className="gv-msg gv-msg-a">
              <div className="gv-bubble gv-bubble-a">
                <div className="thinking-dots"><div className="td" /><div className="td" /><div className="td" /></div>
              </div>
            </div>
          )}
          {streaming && streamText && (
            <div className="gv-msg gv-msg-a">
              <div className="gv-bubble gv-bubble-a">{streamText}<span className="gv-cursor" /></div>
            </div>
          )}
        </div>
      )}

      <div className="gv-input-row">
        <button className="gv-attach-btn" onClick={() => fileRef.current?.click()}>
          <Icon d={Icons.attach} size={13} sw={1.4} />
        </button>
        <input
          ref={inputRef}
          className="gv-input"
          placeholder="Ask about your screen…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          disabled={busy}
        />
        <button className="gv-send" onClick={send} disabled={(!input.trim() && !attached) || busy}>
          <Icon d={Icons.send} size={13} stroke="white" sw={1.8} />
        </button>
      </div>
    </>
  );
}
