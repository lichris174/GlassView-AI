import { Icon } from "./Icon";
import { Icons } from "./icons";
import { TOOLS } from "./tools";
import type { ToolId } from "../types";

interface ToolbarProps {
  open: boolean;
  activeTool: ToolId | null;
  onToggle: (id: ToolId) => void;
}

/** Horizontal tool icon strip that fades/scales into the expanded pill. */
export function Toolbar({ open, activeTool, onToggle }: ToolbarProps) {
  return (
    <div className={`gv-tools${open ? " open" : ""}`}>
      <div className="gv-sep" />
      {TOOLS.map((tool, i) => (
        <button
          key={tool.id}
          className={`gv-tool-btn${activeTool === tool.id ? " active" : ""}`}
          style={{ "--tool-index": i } as React.CSSProperties}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={() => onToggle(tool.id)}
        >
          <Icon d={Icons[tool.icon]} size={15} stroke="currentColor" sw={1.4} />
          <div className="gv-tip">
            <span className="gv-tip-label">{tool.label}</span>
            <span className="gv-tip-kbd">{tool.kbd}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
