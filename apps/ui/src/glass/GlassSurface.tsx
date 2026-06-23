import type { CSSProperties, ReactNode } from "react";
import "./glass.css";

interface GlassSurfaceProps {
  children: ReactNode;
  /** "panel" = large container, "capsule" = compact HUD pill. */
  variant?: "panel" | "capsule";
  className?: string;
  style?: CSSProperties;
}

/**
 * Presentational primitive for the frosted glass material. Consumers route
 * through this so the look can change in one place. The current frost is
 * token-driven; the displacement/glint pass can be added here later.
 */
export function GlassSurface({
  children,
  variant = "panel",
  className = "",
  style,
}: GlassSurfaceProps) {
  return (
    <div className={`glass glass--${variant} ${className}`} style={style}>
      <div className="glass__sheen" aria-hidden />
      <div className="glass__content">{children}</div>
    </div>
  );
}
