import { useCallback, useEffect, useRef, useState } from "react";
import { cancelSnip, finishSnip, getSnipImage, isTauri } from "../lib/tauri";
import "./snip.css";

/**
 * In a plain browser (vite dev, no Tauri) there is no captured screen, so paint
 * a synthetic frame. Lets the overlay's drag/loupe/badge be iterated visually
 * without launching the native shell, the same way preview.html iterates glass.
 */
function devPlaceholder(): string {
  const c = document.createElement("canvas");
  c.width = window.innerWidth;
  c.height = window.innerHeight;
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, c.width, c.height);
  g.addColorStop(0, "#1b3a5b");
  g.addColorStop(0.5, "#b14bd6");
  g.addColorStop(1, "#08060f");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.font = "48px ui-sans-serif, system-ui";
  ctx.fillText("snip preview (no capture in browser)", 60, 120);
  return c.toDataURL("image/png");
}

/** A selection rectangle in CSS pixels, viewport-relative. */
interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const MIN_SIZE = 6; // px; smaller selections are treated as a click, not a snip
const LOUPE_ZOOM = 8;
const LIFT_MS = 160;

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function normalize(a: { x: number; y: number }, b: { x: number; y: number }): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  };
}

function toHex(r: number, g: number, b: number): string {
  const h = (n: number) => n.toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`.toUpperCase();
}

export default function SnipOverlay() {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [scale, setScale] = useState(1); // image (physical) px per CSS px
  const [rect, setRect] = useState<Rect | null>(null);
  const [dragging, setDragging] = useState(false);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [color, setColor] = useState<string | null>(null);
  const [lifting, setLifting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const anchor = useRef<{ x: number; y: number } | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null); // offscreen pixel sampler

  // --- load the frozen capture ---------------------------------------------
  useEffect(() => {
    let alive = true;
    getSnipImage()
      .then((src) => {
        if (!alive) return;
        if (!src) {
          if (!isTauri()) src = devPlaceholder();
          else {
            setError("No capture available. Press Esc to close.");
            return;
          }
        }
        const img = new Image();
        img.onload = () => {
          if (!alive) return;
          const canvas = document.createElement("canvas");
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          canvas.getContext("2d")?.drawImage(img, 0, 0);
          canvasRef.current = canvas;
          setScale(img.naturalWidth / window.innerWidth);
          setImageSrc(src);
        };
        img.onerror = () => alive && setError("Capture failed to decode.");
        img.src = src;
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const close = useCallback(() => void cancelSnip(), []);

  const confirm = useCallback(
    (r: Rect) => {
      if (r.w < MIN_SIZE || r.h < MIN_SIZE) return;
      const send = () =>
        void finishSnip({
          x: r.x,
          y: r.y,
          width: r.w,
          height: r.h,
          viewportW: window.innerWidth,
          viewportH: window.innerHeight,
        });
      if (prefersReducedMotion()) {
        send();
        return;
      }
      setLifting(true);
      window.setTimeout(send, LIFT_MS);
    },
    [],
  );

  // --- pixel sampling under the cursor -------------------------------------
  const sample = useCallback(
    (x: number, y: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const px = Math.floor(x * scale);
      const py = Math.floor(y * scale);
      const data = canvas.getContext("2d")?.getImageData(px, py, 1, 1).data;
      if (data) setColor(toHex(data[0], data[1], data[2]));
    },
    [scale],
  );

  // --- mouse drag ----------------------------------------------------------
  function onMouseDown(e: React.MouseEvent) {
    if (!imageSrc || lifting) return;
    anchor.current = { x: e.clientX, y: e.clientY };
    setDragging(true);
    setRect({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  }

  function onMouseMove(e: React.MouseEvent) {
    setCursor({ x: e.clientX, y: e.clientY });
    sample(e.clientX, e.clientY);
    if (dragging && anchor.current) {
      setRect(normalize(anchor.current, { x: e.clientX, y: e.clientY }));
    }
  }

  function onMouseUp() {
    if (!dragging) return;
    setDragging(false);
    anchor.current = null;
    // Selection stays put so it can be nudged/resized by keyboard, then
    // confirmed with Enter. A too-small drag is discarded as a misclick.
    setRect((r) => (r && (r.w < MIN_SIZE || r.h < MIN_SIZE) ? null : r));
  }

  // --- keyboard: nudge, resize, confirm, cancel ----------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const key = e.key.toLowerCase();
      if (key === "escape" || (key === "m" && e.ctrlKey && e.altKey)) {
        e.preventDefault();
        close();
        return;
      }
      if (key === "enter" && rect) {
        e.preventDefault();
        confirm(rect);
        return;
      }
      if (!rect || dragging) return;
      const step = e.altKey ? 1 : 10;
      const arrows: Record<string, [number, number]> = {
        arrowleft: [-1, 0],
        arrowright: [1, 0],
        arrowup: [0, -1],
        arrowdown: [0, 1],
      };
      const dir = arrows[key];
      if (!dir) return;
      e.preventDefault();
      setRect((r) => {
        if (!r) return r;
        if (e.shiftKey) {
          return {
            ...r,
            w: Math.max(MIN_SIZE, r.w + dir[0] * step),
            h: Math.max(MIN_SIZE, r.h + dir[1] * step),
          };
        }
        return { ...r, x: r.x + dir[0] * step, y: r.y + dir[1] * step };
      });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rect, dragging, confirm, close]);

  // --- loupe geometry ------------------------------------------------------
  const showLoupe = !!imageSrc && !!cursor && (!rect || dragging);
  const loupeSize = 132;
  const loupeStyle =
    showLoupe && cursor && imageSrc
      ? ({
          left: cursor.x + 24,
          top: cursor.y + 24,
          width: loupeSize,
          height: loupeSize,
          backgroundImage: `url(${imageSrc})`,
          backgroundSize: `${window.innerWidth * LOUPE_ZOOM}px ${window.innerHeight * LOUPE_ZOOM}px`,
          backgroundPosition: `${-cursor.x * LOUPE_ZOOM + loupeSize / 2}px ${
            -cursor.y * LOUPE_ZOOM + loupeSize / 2
          }px`,
        } as React.CSSProperties)
      : undefined;

  return (
    <div
      className={`snip${lifting ? " snip--lift" : ""}`}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
    >
      {imageSrc && <img className="snip__frame" src={imageSrc} alt="" draggable={false} />}

      {/* Full scrim before a selection exists; fades in over the frozen frame. */}
      {!rect && <div className="snip__scrim" />}

      {/* Selection punches a bright hole in the scrim via an outset box-shadow. */}
      {rect && (
        <div
          className="snip__selection"
          style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }}
        >
          <span className={`snip__badge${rect.y < 34 ? " snip__badge--inside" : ""}`}>
            {Math.round(rect.w * scale)} &times; {Math.round(rect.h * scale)} px
          </span>
        </div>
      )}

      {showLoupe && loupeStyle && (
        <div className="snip__loupe" style={loupeStyle}>
          <div className="snip__loupe-cross" />
          <div className="snip__loupe-readout">
            {color && <span className="snip__swatch" style={{ background: color }} />}
            <span>
              {Math.round((cursor?.x ?? 0) * scale)}, {Math.round((cursor?.y ?? 0) * scale)}
            </span>
            {color && <span>{color}</span>}
          </div>
        </div>
      )}

      <div className="snip__hint">
        {error ??
          (rect
            ? "Arrows nudge · Shift+Arrows resize · Enter confirm · Esc cancel"
            : "Drag to select · Esc to cancel")}
      </div>
    </div>
  );
}
