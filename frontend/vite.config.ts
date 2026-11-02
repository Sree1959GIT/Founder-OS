/// <reference types="vitest/config" />
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));
const backendUrl = process.env.FOUNDEROS_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(here, "src") },
  },
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": { target: backendUrl, changeOrigin: false },
      "/ws": { target: backendUrl.replace(/^http/, "ws"), ws: true },
    },
  },
  preview: { host: "127.0.0.1", port: 3000, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
