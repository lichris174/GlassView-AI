import { useCallback, useEffect, useState } from "react";
import type { Provider, Settings } from "../types";

const KEY = "glassview.settings";
const API_KEY = "glassview.apiKey";

const DEFAULTS: Settings = {
  provider: "ollama",
  shortcut: "Ctrl+Shift+Space",
  closeOnBlur: true,
  autoLaunch: false,
  streaming: true,
  privacy: true,
  autoContext: true,
};

/**
 * Guess a provider from an API-key prefix. Only a hint for pre-selecting the
 * picker — DeepSeek is unreachable this way because its keys also start with
 * "sk-". The user's explicit choice in Settings is what actually dispatches.
 */
export function detectProvider(key: string): Provider {
  if (!key) return "ollama";
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-")) return "openai";
  return "ollama";
}

export const PROVIDER_LABELS: Record<Provider, string> = {
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
};

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
