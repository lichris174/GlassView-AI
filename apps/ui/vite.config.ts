import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri serves the built assets; in dev it points at this server (port 1420).
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    target: "es2021",
    rollupOptions: {
      input: {
        main: "index.html",
        preview: "preview.html",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
