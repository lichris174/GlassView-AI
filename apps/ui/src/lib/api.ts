import type { ChatDetail, ChatSummary, Health, Message } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE}/health`).then(json<Health>),

  listChats: () =>
    fetch(`${BASE}/chats`).then(json<{ chats: ChatSummary[] }>).then((d) => d.chats),

  newChat: (title?: string) =>
    fetch(`${BASE}/chats`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
      .then(json<{ chat: ChatSummary }>)
      .then((d) => d.chat),

  getChat: (id: string) => fetch(`${BASE}/chats/${id}`).then(json<ChatDetail>),

  renameChat: (id: string, title: string) =>
    fetch(`${BASE}/chats/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).then(json),

  deleteChat: (id: string) =>
    fetch(`${BASE}/chats/${id}`, { method: "DELETE" }).then(json),

  /**
   * Stream a chat turn. Calls onToken for each text chunk; resolves with the
   * full answer. The backend streams plain UTF-8 text (not SSE framing).
   */
  async streamChat(
    req: { chat_id: string; message: string; image?: string },
    onToken: (chunk: string) => void,
    signal?: AbortSignal,
  ): Promise<string> {
    const res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`${res.status} ${await res.text()}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let answer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      answer += chunk;
      onToken(chunk);
    }
    return answer;
  },
};

export type { ChatDetail, ChatSummary, Health, Message };
