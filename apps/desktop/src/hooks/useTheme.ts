import { useEffect, useState } from "react";
import { applyTheme } from "../styles/tokens";
import type { ThemeName } from "../types";

const KEY = "glassview.theme";

/** Dark/light theme, persisted to localStorage, applied as --gv-* CSS vars on :root. */
export function useTheme() {
  const [theme, setTheme] = useState<ThemeName>(() => {
    const saved = localStorage.getItem(KEY);
    return saved === "light" ? "light" : "dark";
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(KEY, theme);
  }, [theme]);

  return { theme, setTheme };
}
