import { useCallback, useEffect, useState } from "react";
import type { Provider, Settings } from "../types";

const KEY = "glassview.settings";
const API_KEY = "glassview.apiKey";

const DEFAULTS: Settings = {
  shortcut: "Ctrl+Shift+Space",
  closeOnBlur: true,
  autoLaunch: false,
  streaming: true,
  privacy: true,
  autoContext: true,
};

/** Detect provider from an API-key prefix (brief's detectProvider). */
export function detectProvider(key: string): Provider {
  if (!key) return "ollama";
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-")) return "openai";
  return "ollama";
}

/** Settings + API key, persisted to localStorage and re-applied on load. */
export function useSettings() {
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
    } catch {
      return DEFAULTS;
    }
  });
  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem(API_KEY) ?? "");

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    localStorage.setItem(API_KEY, apiKey);
  }, [apiKey]);

  const update = useCallback(<K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((s) => ({ ...s, [key]: value }));
  }, []);

  return { settings, setSettings, update, apiKey, setApiKey };
}
