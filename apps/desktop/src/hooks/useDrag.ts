import { useCallback, useEffect, useRef, useState } from "react";
import type { Pos } from "../types";

/**
 * Pointer-drag position for the pill. Pass the initial position; returns the current
 * position and an onMouseDown handler to spread onto the draggable element. The pill
 * floats freely (no edge snapping) per the brief. Ported from the mockup's bar-drag
 * logic (lines 620-638) and generalized into a hook.
 */
const DRAG_THRESHOLD = 4; // px before a press counts as a drag (vs a click)

export function useDrag(initial: Pos) {
  const [pos, setPos] = useState<Pos>(initial);
  const [dragging, setDragging] = useState(false);
  const origin = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);
  // True once a press has moved past the threshold. Lets the logo double as a drag
  // handle: the click handler checks this to skip expand/collapse after a real drag.
  const moved = useRef(false);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      origin.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y };
      moved.current = false;
      setDragging(true);
      e.preventDefault();
    },
    [pos],
  );

  useEffect(() => {
    if (!dragging) return;
    const move = (e: MouseEvent) => {
      const o = origin.current;
      if (!o) return;
      const dx = e.clientX - o.mx;
      const dy = e.clientY - o.my;
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) moved.current = true;
      setPos({ x: o.px + dx, y: o.py + dy });
    };
    const up = () => setDragging(false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [dragging]);

  return { pos, setPos, dragging, moved, onMouseDown };
}
