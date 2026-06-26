import { useCallback, useRef, useState } from "react";
import { api, type ApiMessage } from "../api/client";
import type { Message } from "../types";

function toUiMessages(msgs: ApiMessage[]): Message[] {
  return msgs
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ role: m.role as Message["role"], text: m.content }));
}

/**
 * Owns one conversation: lazily creates a chat_id, sends turns to the streaming /chat
 * endpoint, and exposes the running transcript + thinking/streaming flags. onDone fires
 * when an assistant turn finishes (used to raise the collapsed-notif pulse).
 */
export function useChat(onDone?: () => void) {
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [thinking, setThinking] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const busy = thinking || streaming;
  const cancelled = useRef(false);

  const ensureChat = useCallback(async (): Promise<string> => {
    if (chatId) return chatId;
    const { chat } = await api.createChat();
    setChatId(chat.id);
    return chat.id;
  }, [chatId]);

  const send = useCallback(
    async (text: string, image?: string) => {
      const msg = text.trim();
      if ((!msg && !image) || busy) return;
      cancelled.current = false;
      // Only show a user bubble when text was actually sent. Image-only turns
      // rely on the backend's default prompt ("Describe this screenshot briefly.").
      if (msg) setMessages((m) => [...m, { role: "user", text: msg }]);
      setThinking(true);
      setStreamText("");

      try {
        const id = await ensureChat();
        let acc = "";
        for await (const chunk of api.chat(id, msg, image)) {
          if (cancelled.current) break;
          acc += chunk;
          setThinking(false);
          setStreaming(true);
          setStreamText(acc);
        }
        if (cancelled.current) {
          // If we received partial text before a switch/reset, keep it so the
          // user isn't left with a dangling user bubble.
          if (acc) {
            setMessages((m) => [...m, { role: "assistant", text: `${acc}\n\n[cancelled]` }]);
          }
        } else {
          const answer = acc || "(no response)";
          setMessages((m) => [...m, { role: "assistant", text: answer }]);
          onDone?.();
        }
      } catch (e) {
        setMessages((m) => [
          ...m,
          { role: "assistant", text: `[error] ${(e as Error).message}` },
        ]);
      } finally {
        setThinking(false);
        setStreaming(false);
        setStreamText("");
      }
    },
    [busy, ensureChat, onDone],
  );

  /** Load an existing chat (from History) into this panel. */
  const load = useCallback(async (id: string) => {
    cancelled.current = true;
    const detail = await api.getChat(id);
    setChatId(detail.id);
    setMessages(toUiMessages(detail.messages));
    setThinking(false);
    setStreaming(false);
    setStreamText("");
  }, []);

  const reset = useCallback(() => {
    cancelled.current = true;
    setChatId(null);
    setMessages([]);
    setThinking(false);
    setStreaming(false);
    setStreamText("");
  }, []);

  return { chatId, messages, thinking, streaming, streamText, busy, send, load, reset };
}
