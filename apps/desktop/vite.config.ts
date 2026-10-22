import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Single overlay entry. Region selection runs inside the main window now (no second
// window), so there is no separate snip page to build. Tauri serves on a fixed port.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
});
