import { useEffect, useMemo, useState } from "react";
import { api, type ChatSummary } from "../../api/client";
import { Icon } from "../Icon";
import { Icons } from "../icons";

interface HistoryPanelProps {
  onOpen: (chatId: string) => void;
  /** Lets the parent drop the open conversation if it was the one deleted. */
  onDeleted: (chatId: string) => void;
  visible: boolean;
}

/** Relative "2m ago" / "3h ago" from an ISO/SQL timestamp. */
function relTime(ts: string | null): string {
  if (!ts) return "";
  const then = new Date(ts.includes("T") ? ts : ts.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 172800) return "Yesterday";
  return `${Math.floor(s / 86400)}d ago`;
}

export function HistoryPanel({ onOpen, onDeleted, visible }: HistoryPanelProps) {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  // Chat awaiting confirmation. A second click on the same row confirms — no
  // window.confirm(), which would freeze the webview in the Tauri overlay.
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    let alive = true;
    setLoading(true);
    setPendingDelete(null);
    api
      .listChats()
      .then((r) => alive && setChats(r.chats))
      .catch(() => alive && setChats([]))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [visible]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return chats.filter((c) => c.title.toLowerCase().includes(q));
  }, [chats, query]);

  const remove = async (id: string) => {
    // Optimistic: the row goes immediately, and a failure puts it back.
    const previous = chats;
    setChats((cs) => cs.filter((c) => c.id !== id));
    setPendingDelete(null);
    try {
      await api.deleteChat(id);
      onDeleted(id);
    } catch {
      setChats(previous);
    }
  };

  return (
    <>
      <input
        className="gv-hist-search"
        placeholder="Search past chats…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      <div className="gv-hist-list">
        {loading ? (
          <div className="gv-hist-empty">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="gv-hist-empty">{chats.length === 0 ? "No chats yet" : "No matches"}</div>
        ) : (
          filtered.map((c) => (
            <div key={c.id} className="gv-hist-item" onClick={() => onOpen(c.id)}>
              <div className="gv-hist-row">
                <span className="gv-hist-title">{c.title || "Untitled"}</span>
                <span className="gv-hist-time">{relTime(c.updated_at)}</span>
                <button
                  className={`gv-hist-del${pendingDelete === c.id ? " confirm" : ""}`}
                  title={pendingDelete === c.id ? "Click again to delete" : "Delete chat"}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (pendingDelete === c.id) remove(c.id);
                    else setPendingDelete(c.id);
                  }}
                >
                  {pendingDelete === c.id ? (
                    "Delete?"
                  ) : (
                    <Icon d={Icons.trash} size={11} sw={1.5} />
                  )}
                </button>
              </div>
              <div className="gv-hist-preview">{c.message_count} messages</div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
