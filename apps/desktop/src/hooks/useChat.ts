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
  // Each turn gets a generation number and its own AbortController. Switching or
  // resetting the chat bumps the generation and aborts the request, so a stale
  // turn can never write its answer into whichever chat is loaded now.
  const generation = useRef(0);
  const inFlight = useRef<AbortController | null>(null);

  // The aborted turn skips its own cleanup (it is no longer current), so the
  // busy flags are cleared here; otherwise a failed load would leave the input
  // stuck in the busy state.
  const cancelInFlight = useCallback(() => {
    generation.current += 1;
    inFlight.current?.abort();
    inFlight.current = null;
    setThinking(false);
    setStreaming(false);
    setStreamText("");
  }, []);

  const ensureChat = useCallback(async (): Promise<string> => {
    if (chatId) return chatId;
    const { chat } = await api.createChat();
    setChatId(chat.id);
    return chat.id;
  }, [chatId]);

  const send = useCallback(
    async (text: string, image?: string) => {
      const msg = text.trim();
      // inFlight is checked too: `busy` is render state, so two sends in the same
      // tick would both see it as false.
      if ((!msg && !image) || busy || inFlight.current) return;
      const gen = ++generation.current;
      const ctrl = new AbortController();
      inFlight.current = ctrl;
      const isCurrent = () => gen === generation.current;

      // Show a user bubble when there is anything to show: text, an attachment,
      // or both. An image-only turn still gets a bubble (with the thumbnail); the
      // backend supplies the default prompt ("Describe this screenshot briefly.").
      setMessages((m) => [
        ...m,
        { role: "user", text: msg, images: image ? [image] : undefined },
      ]);
      setThinking(true);
      setStreamText("");

      try {
        const id = await ensureChat();
        let acc = "";
        const opts = { redact, provider, apiKey, signal: ctrl.signal };
        for await (const chunk of api.chat(id, msg, image, opts)) {
          if (!isCurrent()) return;
          acc += chunk;
          // With streaming off, hold the thinking indicator and reveal the whole
          // answer once the turn completes.
          if (showTokens) {
            setThinking(false);
            setStreaming(true);
            setStreamText(acc);
          }
        }
        if (!isCurrent()) return;
        setMessages((m) => [...m, { role: "assistant", text: acc || "(no response)" }]);
        onDoneRef.current?.();
      } catch (e) {
        // An abort is a deliberate cancel, not an error to show the user.
        if (!isCurrent() || ctrl.signal.aborted) return;
        setMessages((m) => [
          ...m,
          { role: "assistant", text: `[error] ${(e as Error).message}` },
        ]);
      } finally {
        // A newer turn or a chat switch owns these flags now; leave them alone.
        if (isCurrent()) {
          inFlight.current = null;
          setThinking(false);
          setStreaming(false);
          setStreamText("");
        }
      }
    },
    [apiKey, busy, ensureChat, provider, redact, showTokens],
  );

  /** Load an existing chat (from History) into this panel. */
  const load = useCallback(async (id: string) => {
    cancelInFlight();
    const gen = generation.current;
    const detail = await api.getChat(id);
    // A second load or a reset may have happened while this one was fetching.
    if (gen !== generation.current) return;
    setChatId(detail.id);
    setMessages(toUiMessages(detail.messages));
  }, [cancelInFlight]);

  const reset = useCallback(() => {
    cancelInFlight();
    setChatId(null);
    setMessages([]);
  }, [cancelInFlight]);

  return { chatId, messages, thinking, streaming, streamText, busy, send, load, reset };
}
