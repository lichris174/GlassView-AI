// Theme tokens exposed as CSS custom properties (--gv-<key>) that useTheme writes onto
// :root, so global.css references var(--gv-pillBg) etc. and only the variables change.
//
// Palette: "Monochrome Minimal" — a near-black tonal surface ladder, hairline borders,
// muted text that stays neutral (never the old iOS-blue chrome), and a single restrained
// near-white signature accent. Tokens are the only place colour lives, so the whole
// palette stays swappable: rewrite the values here and nothing else needs to move.

import type { ThemeName } from "../types";

export type Tokens = Record<string, string>;

export const T: Record<ThemeName, Tokens> = {
  dark: {
    // surface ladder: body #0A0A0A · s1 #141414 · s2 #1E1E1E · s3 #262626
    bg: "#0A0A0A",
    winBg: "rgba(20,20,20,.96)",
    winBar: "rgba(30,30,30,.95)",
    winBorder: "rgba(255,255,255,.07)",
    pillBg: "#141414",
    pillBorder: "rgba(255,255,255,.09)",
    panelBg: "#141414",
    panelBorder: "rgba(255,255,255,.08)",
    ctxBg: "rgba(255,255,255,.045)",
    ctxBorder: "rgba(255,255,255,.07)",
    inputBg: "rgba(255,255,255,.05)",
    inputBorder: "rgba(255,255,255,.09)",
    inputFocus: "rgba(255,255,255,.3)",
    bubbleAiBg: "rgba(255,255,255,.055)",
    bubbleAiBorder: "rgba(255,255,255,.08)",
    toolColor: "rgba(255,255,255,.45)",
    toolHover: "rgba(255,255,255,.07)",
    titleColor: "rgba(255,255,255,.44)",
    textPrimary: "rgba(250,250,250,.92)",
    textSecondary: "rgba(255,255,255,.55)",
    textFaint: "rgba(255,255,255,.34)",
    sepColor: "rgba(255,255,255,.09)",
    closeBg: "rgba(255,255,255,.07)",
    closeHover: "rgba(255,255,255,.14)",
    histHover: "rgba(255,255,255,.05)",
    settingRowBg: "rgba(255,255,255,.04)",
    settingRowBorder: "rgba(255,255,255,.07)",
    fakeLine: "rgba(255,255,255,.06)",
    errorBg: "rgba(255,69,58,.08)",
    errorBorder: "rgba(255,69,58,.2)",
    errorText: "rgba(255,99,90,.92)",
    errorSub: "rgba(255,99,90,.55)",
    warnIcon: "#FF5A4E",
    bubbleAiText: "rgba(255,255,255,.84)",
    // signature accent — near-white; dark ink sits on top of it
    accent: "#FAFAFA",
    accentHover: "#FFFFFF",
    accentText: "#0A0A0A",
    accentSoft: "rgba(255,255,255,.1)",
    accentBorder: "rgba(255,255,255,.22)",
    accentGlow: "rgba(255,255,255,.18)",
    // Compact elevation. Kept tight on purpose: the Tauri window is fit to content + 2px,
    // so a wide outer glow would be clipped into a hard rectangular halo around the overlay.
    shadow: "0 1px 2px rgba(0,0,0,.45), 0 4px 10px rgba(0,0,0,.4)",
  },
  light: {
    // inverted ladder: body #ECECEC · s1 #FFFFFF · s2 #F4F4F5 · s3 #E7E7E9
    bg: "#ECECEC",
    winBg: "rgba(252,252,253,.98)",
    winBar: "rgba(244,244,245,.98)",
    winBorder: "rgba(0,0,0,.08)",
    pillBg: "#FFFFFF",
    pillBorder: "rgba(0,0,0,.1)",
    panelBg: "#FFFFFF",
    panelBorder: "rgba(0,0,0,.08)",
    ctxBg: "rgba(0,0,0,.035)",
    ctxBorder: "rgba(0,0,0,.07)",
    inputBg: "rgba(0,0,0,.04)",
    inputBorder: "rgba(0,0,0,.08)",
    inputFocus: "rgba(0,0,0,.32)",
    bubbleAiBg: "rgba(0,0,0,.045)",
    bubbleAiBorder: "rgba(0,0,0,.06)",
    toolColor: "rgba(0,0,0,.42)",
    toolHover: "rgba(0,0,0,.05)",
    titleColor: "rgba(0,0,0,.42)",
    textPrimary: "rgba(10,10,10,.9)",
    textSecondary: "rgba(0,0,0,.55)",
    textFaint: "rgba(0,0,0,.4)",
    sepColor: "rgba(0,0,0,.1)",
    closeBg: "rgba(0,0,0,.06)",
    closeHover: "rgba(0,0,0,.12)",
    histHover: "rgba(0,0,0,.04)",
    settingRowBg: "rgba(0,0,0,.03)",
    settingRowBorder: "rgba(0,0,0,.07)",
    fakeLine: "rgba(0,0,0,.08)",
    errorBg: "rgba(214,40,30,.07)",
    errorBorder: "rgba(214,40,30,.2)",
    errorText: "rgba(190,35,26,.92)",
    errorSub: "rgba(190,35,26,.6)",
    warnIcon: "#D6281E",
    bubbleAiText: "rgba(0,0,0,.8)",
    accent: "#1A1A1A",
    accentHover: "#000000",
    accentText: "#FAFAFA",
    accentSoft: "rgba(0,0,0,.07)",
    accentBorder: "rgba(0,0,0,.2)",
    accentGlow: "rgba(0,0,0,.14)",
    shadow: "0 1px 2px rgba(0,0,0,.12), 0 4px 10px rgba(0,0,0,.12)",
  },
};

/** Write a theme's tokens onto :root as --gv-<key> custom properties. */
export function applyTheme(theme: ThemeName): void {
  const tokens = T[theme];
  const root = document.documentElement;
  for (const [key, value] of Object.entries(tokens)) {
    root.style.setProperty(`--gv-${key}`, value);
  }
  root.dataset.theme = theme;
}
