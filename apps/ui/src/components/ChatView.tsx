import { useEffect, useRef } from "react";
import { Message } from "./Message";
import type { Message as MessageT } from "../lib/types";

/** Scrollable message list; auto-sticks to bottom while streaming. */
export function ChatView({ messages }: { messages: MessageT[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat__scroll">
      {messages.length === 0 && (
        <div className="msg msg--assistant" style={{ color: "var(--fg-muted)" }}>
          Capture your screen and ask a question to get started.
        </div>
      )}
      {messages.map((m, i) => (
        <Message key={i} message={m} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
