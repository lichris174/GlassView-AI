import { useCallback, useRef, useState } from "react";
import { api, type ApiMessage } from "../api/client";
import type { Message } from "../types";

function toUiMessages(msgs: ApiMessage[]): Message[] {
  return msgs
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      role: m.role as Message["role"],
      text: m.content,
      // Carry the stored attachments through so a reopened chat still shows them.
      images: m.images?.length ? m.images : undefined,
    }));
}

export interface UseChatOptions {
  /** Settings → "Stream responses". When false the answer appears in one go and the
   *  thinking indicator stays up until it is complete. The request is streamed either
   *  way; this only decides whether partial text is rendered. */
  streaming?: boolean;
  /** Settings → "Privacy redaction". Forwarded to the backend for memory writes. */
  redact?: boolean;
  /** Which backend answers the turn. "ollama" keeps everything on-device. */
  provider?: string;
  /** Cloud key, sent per-request and never persisted server-side. */
  apiKey?: string;
  /** Fires when an assistant turn finishes (raises the collapsed-notif pulse). */
  onDone?: () => void;
}

/**
 * Owns one conversation: lazily creates a chat_id, sends turns to the streaming /chat
 * endpoint, and exposes the running transcript + thinking/streaming flags.
 */
export function useChat(options: UseChatOptions = {}) {
  const { streaming: showTokens = true, redact = true, provider, apiKey } = options;
  // Held in a ref so an inline onDone from the caller does not rebuild `send`.
  const onDoneRef = useRef(options.onDone);
  onDoneRef.current = options.onDone;
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
      // Show a user bubble when there is anything to show — text, an attachment,
      // or both. An image-only turn still gets a bubble (with the thumbnail); the
      // backend supplies the default prompt ("Describe this screenshot briefly.").
      if (msg || image) {
        setMessages((m) => [
          ...m,
          { role: "user", text: msg, images: image ? [image] : undefined },
        ]);
      }
      setThinking(true);
      setStreamText("");

      try {
        const id = await ensureChat();
        let acc = "";
        for await (const chunk of api.chat(id, msg, image, { redact, provider, apiKey })) {
          if (cancelled.current) break;
          acc += chunk;
          // With streaming off, hold the thinking indicator and reveal the whole
          // answer once the turn completes.
          if (showTokens) {
            setThinking(false);
            setStreaming(true);
            setStreamText(acc);
          }
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
          onDoneRef.current?.();
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
    [apiKey, busy, ensureChat, provider, redact, showTokens],
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
