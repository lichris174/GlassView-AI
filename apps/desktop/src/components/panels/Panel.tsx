import type { ReactNode } from "react";
import { Icon } from "../Icon";
import { Icons } from "../icons";

/** Where the panel scales from: the tool button that opened it. */
export interface PanelOrigin {
  /** Horizontal offset of the button's centre from the panel's left edge. */
  x: number;
  /** How far *below* the panel's bottom edge the button's centre sits. */
  dy: number;
}

interface PanelProps {
  title: string;
  onClose: () => void;
  origin: PanelOrigin;
  /** True while the panel is minimizing back into its button, before unmount. */
  closing?: boolean;
  children: ReactNode;
}

/**
 * Glass panel anchored above the pill: uppercase title header + close button.
 *
 * It opens and closes the way a Windows window restores and minimizes — scaling
 * out of, and back into, the tool button that owns it. The button sits below the
 * panel, so the transform origin is expressed as `calc(100% + dy)` vertically:
 * 100% is the panel's own bottom edge, and dy carries the point down onto the
 * button regardless of how tall this particular panel is.
 *
 * The panel keeps its natural height. An earlier version animated the height
 * between tools, which is what still read as "snapping" — the box resized while
 * the content changed under it. Scaling from the button replaces that entirely.
 */
export function Panel({ title, onClose, origin, closing, children }: PanelProps) {
  return (
    <div
      className={`gv-panel${closing ? " closing" : ""}`}
      style={{ transformOrigin: `${origin.x}px calc(100% + ${origin.dy}px)` }}
    >
      <div className="gv-panel-hdr">
        <span className="gv-panel-title">{title}</span>
        <button className="gv-close-btn" onClick={onClose}>
          <Icon d={Icons.close} size={10} sw={2} />
        </button>
      </div>
      {children}
    </div>
  );
}
