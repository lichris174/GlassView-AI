// Typed wrappers for the GlassView backend (FastAPI on 127.0.0.1:8765).
// See README.md "HTTP API". Streaming /chat returns plain text/plain token chunks
// (not SSE) — read the body reader and decode incrementally.

export const BASE_URL = "http://127.0.0.1:8765";

export interface Health {
  status: string; // "ok", or "degraded" when no local model is available
  model: string | null;
  model_error: string | null;
  ollama_host: string;
  providers: string[];
}

export interface ChatSummary {
  id: string;
  title: string;
  updated_at: string | null;
  message_count: number;
}

export interface ApiMessage {
  role: string; // "user" | "assistant"
  content: string;
  images: string[];
}

export interface ChatDetail {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  messages: ApiMessage[];
}

export interface RecallHit {
  text: string;
  distance: number;
  meta: Record<string, unknown>;
  created_at: string;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE_URL}/health`).then((r) => json<Health>(r)),

  listChats: () =>
    fetch(`${BASE_URL}/chats`).then((r) => json<{ chats: ChatSummary[] }>(r)),

  getChat: (id: string) =>
    fetch(`${BASE_URL}/chats/${id}`).then((r) => json<ChatDetail>(r)),

  createChat: (title?: string) =>
    fetch(`${BASE_URL}/chats`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title ?? null }),
    }).then((r) => json<{ chat: ChatSummary }>(r)),

  deleteChat: (id: string) =>
    fetch(`${BASE_URL}/chats/${id}`, { method: "DELETE" }).then((r) =>
      json<{ ok: boolean }>(r),
    ),

  recall: (q: string, k = 5) =>
    fetch(`${BASE_URL}/recall?q=${encodeURIComponent(q)}&k=${k}`).then((r) =>
      json<{ hits: RecallHit[] }>(r),
    ),

  /**
   * Stream a turn. Yields decoded token chunks as they arrive. `image` is sent only
   * when a fresh capture/attachment exists — otherwise the backend reuses the chat's
   * last image. Backend surfaces failures inline as a chunk starting with "[error]".
   *
   * `redact` (Settings → Privacy redaction) controls whether the backend masks
   * secrets before writing this turn to memory. It defaults to true server-side,
   * so omitting it can only ever be the safe choice.
   *
   * `signal` aborts the HTTP request itself, so a cancelled turn stops streaming
   * instead of running to completion in the background.
   */
  async *chat(
    chatId: string,
    message: string,
    image?: string,
    opts: { redact?: boolean; provider?: string; apiKey?: string; signal?: AbortSignal } = {},
  ): AsyncGenerator<string> {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: opts.signal,
      body: JSON.stringify({
        chat_id: chatId,
        message,
        image: image ?? null,
        redact: opts.redact ?? true,
        // Omitted entirely for local Ollama so the backend keeps its default path.
        provider: opts.provider ?? null,
        api_key: opts.apiKey || null,
      }),
    });
    if (!res.ok || !res.body) {
      // FastAPI errors carry a human-readable `detail` (e.g. "Cannot reach Ollama").
      const detail = await res.json().then((b) => b?.detail, () => null);
      throw new Error(detail ? String(detail) : `chat failed: ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield decoder.decode(value, { stream: true });
    }
  },
};
