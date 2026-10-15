import type { Tool } from "../types";

// The tools shown in the expanded toolbar, in order. Ported from the mockup's TOOLS.
export const TOOLS: Tool[] = [
  { id: "chat", label: "Chat", kbd: "C", icon: "chat" },
  { id: "region", label: "Region", kbd: "R", icon: "region" },
  { id: "history", label: "Past Chats", kbd: "H", icon: "history" },
  { id: "settings", label: "Settings", kbd: "S", icon: "settings" },
];
