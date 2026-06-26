import { useEffect, useRef, useState } from "react";

interface Box { x: number; y: number; w: number; h: number; }

interface RegionSelectProps {
  image: string; // PNG data URL of the full screen (physical pixels)
  onDone: (croppedDataUrl: string) => void;
  onCancel: () => void;
}

/**
 * Fullscreen region selector rendered inside the MAIN window. Shows the captured screen,
 * lets the user drag a rectangle, and crops it client-side with a canvas (handling the
 * HiDPI scale between CSS pixels and the physical capture). Escapable via the Cancel
 * button, the parent's Esc handler, and the Rust global-Escape failsafe.
 */
export function RegionSelect({ image, onDone, onCancel }: RegionSelectProps) {
  const [box, setBox] = useState<Box | null>(null);
  const [dragging, setDragging] = useState(false);
  const start = useRef<{ x: number; y: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  // Mirror of `box` so the window-level mouseup listener always sees the latest selection.
  const boxRef = useRef<Box | null>(null);
  boxRef.current = box;

  const crop = (b: Box) => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return onCancel();
    const sx = img.naturalWidth / window.innerWidth;
    const sy = img.naturalHeight / window.innerHeight;
    const cw = Math.max(1, Math.round(b.w * sx));
    const ch = Math.max(1, Math.round(b.h * sy));
    const canvas = document.createElement("canvas");
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext("2d");
    if (!ctx) return onCancel();
    ctx.drawImage(img, b.x * sx, b.y * sy, cw, ch, 0, 0, cw, ch);
    onDone(canvas.toDataURL("image/png"));
  };

  const finishDrag = () => {
    setDragging(false);
    const b = boxRef.current;
    if (b && b.w > 8 && b.h > 8) crop(b);
    else setBox(null);
  };

  const onDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest(".region-cancel")) return;
    start.current = { x: e.clientX, y: e.clientY };
    setDragging(true);
    setBox({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  };
  const onMove = (e: React.MouseEvent) => {
    if (!dragging || !start.current) return;
    const s = start.current;
    setBox({
      x: Math.min(e.clientX, s.x),
      y: Math.min(e.clientY, s.y),
      w: Math.abs(e.clientX - s.x),
      h: Math.abs(e.clientY - s.y),
    });
  };

  // Capture mouseup at the window level so releasing outside the overlay still
  // finishes the selection (the Rust global Escape remains the ultimate failsafe).
  useEffect(() => {
    if (!dragging) return;
    window.addEventListener("mouseup", finishDrag);
    return () => window.removeEventListener("mouseup", finishDrag);
  }, [dragging]);

  return (
    <div className="region-overlay" onMouseDown={onDown} onMouseMove={onMove}>
      <img ref={imgRef} className="region-shot" src={image} alt="" />
      <div className="region-bg" />
      {!dragging && !box && (
        <div className="region-hint">
          <div className="region-hint-t">Select a region</div>
          <div className="region-hint-s">Click and drag · Esc to cancel</div>
        </div>
      )}
      {box && box.w > 2 && (
        <div className="region-sel" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />
      )}
      <button className="region-cancel" onClick={onCancel}>Cancel — esc</button>
    </div>
  );
}
