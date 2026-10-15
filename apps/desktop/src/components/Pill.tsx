import { GLogo } from "./GLogo";
import { Toolbar } from "./Toolbar";
import { TOOLS } from "./tools";
import type { ToolId } from "../types";

interface PillProps {
  expanded: boolean;
  activeTool: ToolId | null;
  hasNotif: boolean;
  onLogoClick: () => void;
  onToggleTool: (id: ToolId) => void;
  onDragMouseDown: (e: React.MouseEvent) => void;
}

/**
 * The draggable pill: G logo button on the left, sliding toolbar on the right.
 * Dragging is initiated by mousedown anywhere on the pill except the buttons
 * (they stopPropagation). The panel (later milestones) anchors above this wrapper.
 */
export function Pill({
  expanded,
  activeTool,
  hasNotif,
  onLogoClick,
  onToggleTool,
  onDragMouseDown,
}: PillProps) {
  return (
    <div
      className={`gv-pill${expanded ? " expanded" : ""}`}
      onMouseDown={onDragMouseDown}
      style={{ "--tool-count": TOOLS.length } as React.CSSProperties}
    >
      {/* Scaled background shell: visually grows from the logo outward while the
          content layout stays stable. */}
      <div className="gv-pill-bg" aria-hidden="true" />
      {/* No stopPropagation here: mousedown falls through to the pill so the whole logo
          is a drag handle (even when expanded). onLogoClick ignores the click if a drag
          actually happened. */}
      <button className="gv-logo-btn" onClick={onLogoClick}>
        <GLogo size={22} animate={hasNotif && !expanded} />
      </button>
      <Toolbar open={expanded} activeTool={activeTool} onToggle={onToggleTool} />
    </div>
  );
}
