import { useState, type KeyboardEvent } from "react";

interface ComposerProps {
  pendingImage: string | null;
  busy: boolean;
  onSend: (message: string) => void;
  onClearImage: () => void;
  onCaptureFull: () => void;
  onSnip: () => void;
}

export function Composer({
  pendingImage,
  busy,
  onSend,
  onClearImage,
  onCaptureFull,
  onSnip,
}: ComposerProps) {
  const [text, setText] = useState("");

  const submit = () => {
    const msg = text.trim();
    if (!msg && !pendingImage) return;
    onSend(msg);
    setText("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer">
      {pendingImage && (
        <div className="composer__preview">
          <img src={pendingImage} alt="pending capture" />
          <span>Screenshot attached</span>
          <button onClick={onClearImage}>Remove</button>
        </div>
      )}
      <div className="composer__row">
        <button onClick={onCaptureFull} disabled={busy} title="Capture full screen">
          Screen
        </button>
        <button onClick={onSnip} disabled={busy} title="Snip a region">
          Region
        </button>
        <textarea
          value={text}
          placeholder="Ask about your screen... (Enter to send)"
          rows={1}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
        />
        <button onClick={submit} disabled={busy}>
          {busy ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
