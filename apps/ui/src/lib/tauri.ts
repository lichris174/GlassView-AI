/**
 * Bridge to the native Tauri shell. Every call is guarded so the UI also runs
 * in a plain browser during `vite dev` (where __TAURI__ is absent).
 */
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const isTauri = (): boolean =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Capture the full primary screen; returns a PNG data URL, or null in browser. */
export async function captureFullscreen(): Promise<string | null> {
  if (!isTauri()) return null;
  return invoke<string>("capture_fullscreen");
}

/** Begin the region-snip flow (overlay window). No-op in browser. */
export async function startSnip(): Promise<void> {
  if (!isTauri()) return;
  await invoke("start_snip");
}

/** Subscribe to a native event; returns an unlisten fn (no-op in browser). */
export async function onNative<T>(
  event: "snip-complete" | "snip-cancel" | "snip-hotkey",
  handler: (payload: T) => void,
): Promise<UnlistenFn> {
  if (!isTauri()) return () => {};
  return listen<T>(event, (e) => handler(e.payload));
}
