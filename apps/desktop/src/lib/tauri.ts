// Thin bridge over the Tauri API that degrades to no-ops in a plain browser, so the
// same React app runs both in `vite dev` (browser) and inside the native shell.

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow, currentMonitor } from "@tauri-apps/api/window";
import { PhysicalPosition, PhysicalSize } from "@tauri-apps/api/dpi";
import { openUrl } from "@tauri-apps/plugin-opener";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

// ── Events from Rust ────────────────────────────────────────────────────────
export function onToggleOverlay(cb: () => void): Promise<UnlistenFn> {
  if (!isTauri()) return Promise.resolve(() => {});
  return listen("toggle-overlay", () => cb());
}
/** Fired by the Rust global-Escape failsafe when region mode is force-cancelled. */
export function onRegionCancel(cb: () => void): Promise<UnlistenFn> {
  if (!isTauri()) return Promise.resolve(() => {});
  return listen("region-cancel", () => cb());
}

// ── Commands ────────────────────────────────────────────────────────────────
/** Capture the primary screen as a PNG data URL (null in a plain browser). */
export const captureScreen = () =>
  isTauri() ? invoke<string>("capture_screen") : Promise.resolve<string | null>(null);
export const armRegionEscape = () =>
  isTauri() ? invoke("arm_region_escape") : Promise.resolve();
export const disarmRegionEscape = () =>
  isTauri() ? invoke("disarm_region_escape") : Promise.resolve();
export const registerShortcut = (accelerator: string) =>
  isTauri() ? invoke("register_shortcut", { accelerator }) : Promise.resolve();

/** Open an http(s) link in the system browser. The webview drops target="_blank"
 *  navigations on its own, so links must go through the opener plugin; a plain
 *  browser just opens a new tab. */
export async function openExternal(url: string): Promise<void> {
  if (!isTauri()) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  await openUrl(url);
}

// ── Launch on login (tauri-plugin-autostart) ────────────────────────────────
// Called through the plugin's command names rather than its JS package so the
// browser build needs no extra dependency to tree-shake away.
export async function setAutostart(on: boolean): Promise<void> {
  if (!isTauri()) return;
  await invoke(on ? "plugin:autostart|enable" : "plugin:autostart|disable");
}

/** The OS is the source of truth — the stored setting is only a cache of it. */
export async function isAutostartEnabled(): Promise<boolean> {
  if (!isTauri()) return false;
  return invoke<boolean>("plugin:autostart|is_enabled");
}

/** Full-screen the overlay for region selection (and back). Suppresses anchor tracking
 *  so the fullscreen move doesn't clobber the pill's resting position. */
export async function setFullscreen(on: boolean): Promise<void> {
  if (!isTauri()) return;
  suppressAnchor = true;
  await getCurrentWindow().setFullscreen(on).catch(() => {});
  if (!on) {
    // Let the restore settle before re-enabling anchor tracking.
    setTimeout(() => { suppressAnchor = false; }, 120);
  }
}

// ── Native window drag (whole-logo drag handle) ─────────────────────────────
export function startDragging(): void {
  if (!isTauri()) return;
  getCurrentWindow().startDragging().catch(() => {});
}

// ── Content-fit sizing, logo anchored ───────────────────────────────────────
// The logo's bottom-left screen corner is pinned: the toolbar grows rightward and the
// panel grows upward without moving the logo. The window is only shifted (logo moves)
// when growth would run off the right/top edge of the monitor. `anchor` follows the
// window when the user drags it (see watchWindowMoves), so reopening a tool doesn't
// snap back to the original spot.
let anchor: { x: number; y: number } | null = null;
let programmatic = false; // true while we move the window ourselves (ignore onMoved)
let suppressAnchor = false; // true during region fullscreen (ignore onMoved)
let lastW = 0;
let lastH = 0;

// Keep the window at least as wide as the widest panel so opening/closing tools
// only changes height, not width. This prevents the anchored pill from sliding
// horizontally every time a panel opens.
const MIN_CONTENT_WIDTH = 342;

/** Measure pill + panel (transform-independent) → the CSS box the window must cover.
 *
 *  Mid-switch two panels are mounted: the outgoing one minimizing and the incoming
 *  one maximizing. Size to the incoming panel (`:not(.closing)`) so the window
 *  lands on the box it is about to need. offsetHeight ignores the scale transform,
 *  so the size is the panel's final one from the first frame — the window is
 *  correct before the animation plays, and the extra area is transparent anyway. */
function contentSize(wrap: HTMLElement): { w: number; h: number } {
  const pill = wrap.querySelector<HTMLElement>(".gv-pill");
  const panel = wrap.querySelector<HTMLElement>(".gv-panel:not(.closing)");
  const pw = pill?.offsetWidth ?? 0;
  const ph = pill?.offsetHeight ?? 0;
  const naW = panel?.offsetWidth ?? 0;
  const naH = panel?.offsetHeight ?? 0;
  const gap = panel ? 10 : 0;
  return { w: Math.max(pw, naW), h: naH + gap + ph };
}

export async function fitWindowToContent(wrap: HTMLElement): Promise<void> {
  if (!isTauri()) return;
  const win = getCurrentWindow();
  const scale = await win.scaleFactor();
  const { w, h } = contentSize(wrap);
  if (w === 0 || h === 0) return;
  const contentW = Math.max(w, MIN_CONTENT_WIDTH);
  const wp = Math.ceil((contentW + 2) * scale);
  const hp = Math.ceil((h + 2) * scale);

  const mon = await currentMonitor();
  const margin = Math.round(14 * scale);
  const taskbar = Math.round(48 * scale);
  const mx = mon?.position.x ?? 0;
  const my = mon?.position.y ?? 0;
  const mw = mon?.size.width ?? wp + 2 * margin;
  const mh = mon?.size.height ?? hp + 2 * margin;

  if (!anchor) {
    anchor = { x: mx + mw - margin - wp, y: my + mh - margin - taskbar };
  }

  // Clamp so the window stays on-screen; only then does the logo shift (edge case).
  const left = Math.max(mx + margin, Math.min(anchor.x, mx + mw - margin - wp));
  const top = Math.max(my + margin, anchor.y - hp);

  programmatic = true;
  const sizeChanged = wp !== lastW || hp !== lastH;
  // Order the two ops by growth direction so the bottom edge (where the pill sits) never
  // overshoots mid-resize — that overshoot is what made the toolbar flash. Growing: move the
  // top up first, then extend height down to it. Shrinking: trim height first, then settle.
  if (hp > lastH) {
    await win.setPosition(new PhysicalPosition(left, top));
    if (sizeChanged) await win.setSize(new PhysicalSize(wp, hp));
  } else {
    if (sizeChanged) await win.setSize(new PhysicalSize(wp, hp));
    await win.setPosition(new PhysicalPosition(left, top));
  }
  lastW = wp;
  lastH = hp;
  setTimeout(() => { programmatic = false; }, 60);
}

/** Keep the anchor in sync when the user drags the window, so reopening a tool grows
 *  from where they left it instead of snapping back. */
export async function watchWindowMoves(): Promise<() => void> {
  if (!isTauri()) return () => {};
  const win = getCurrentWindow();
  return win.onMoved(async ({ payload }) => {
    if (programmatic || suppressAnchor) return;
    const size = await win.innerSize();
    anchor = { x: payload.x, y: payload.y + size.height };
  });
}
