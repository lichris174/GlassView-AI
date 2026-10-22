// Shared types for the GlassView overlay.

export type ThemeName = "dark" | "light";

export type ToolId = "chat" | "region" | "history" | "settings";

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

export type Provider = "ollama" | "openai" | "anthropic" | "deepseek";

export interface Settings {
  /** Chosen explicitly: DeepSeek keys share OpenAI's "sk-" prefix, so the
   *  provider cannot be inferred from the key alone. */
  provider: Provider;
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
  /** Attachments sent with this turn (data URLs or bare base64). Persisted by the
   *  backend on the message row, so reopening a past chat shows them again. */
  images?: string[];
}
