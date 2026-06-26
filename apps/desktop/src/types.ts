// Shared types for the GlassView overlay.

export type ThemeName = "dark" | "light";

export type ToolId = "chat" | "region" | "voice" | "history" | "settings";

export interface Tool {
  id: ToolId;
  label: string;
  kbd: string;
  icon: keyof typeof import("./components/icons").Icons;
}

export interface Pos {
  x: number;
  y: number;
}

export type Provider = "ollama" | "openai" | "anthropic";

export interface Settings {
  shortcut: string;
  closeOnBlur: boolean;
  autoLaunch: boolean;
  streaming: boolean;
  privacy: boolean;
  autoContext: boolean;
}

export interface Message {
  role: "user" | "assistant";
  text: string;
}
