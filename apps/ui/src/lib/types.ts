export interface ChatSummary {
  id: string;
  title: string;
  updated_at: string | null;
  message_count: number;
}

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  images?: string[];
}

export interface ChatDetail {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  messages: Message[];
}

export interface Health {
  status: string;
  model: string;
  ollama_host: string;
}
