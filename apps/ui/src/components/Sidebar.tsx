import { GlassSurface } from "../glass/GlassSurface";
import type { ChatSummary } from "../lib/types";

interface SidebarProps {
  chats: ChatSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function Sidebar({ chats, activeId, onSelect, onNew, onDelete }: SidebarProps) {
  return (
    <GlassSurface className="sidebar">
      <button onClick={onNew}>+ New chat</button>
      <div className="sidebar__title">History</div>
      <div className="sidebar__list">
        {chats.length === 0 && <div className="sidebar__title">No chats yet</div>}
        {chats.map((c) => (
          <div
            key={c.id}
            className={`chat-item ${c.id === activeId ? "chat-item--active" : ""}`}
            onClick={() => onSelect(c.id)}
          >
            <span>{c.title}</span>
            <button
              className="chat-item__del"
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(c.id);
              }}
            >
              x
            </button>
          </div>
        ))}
      </div>
    </GlassSurface>
  );
}
