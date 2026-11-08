import { defineConfig } from "@playwright/test";

// Smoke test: the real backend with a scripted model (backend/tests/e2e_app.py), no Ollama, GPU or network.
const python = process.env.E2E_PYTHON ?? (process.platform === "win32" ? "..\\.venv\\Scripts\\python.exe" : "python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:3021", viewport: { width: 1440, height: 900 } },
  reporter: [["list"]],
  webServer: [
    {
      command: `${python} -m uvicorn tests.e2e_app:create_e2e_app --factory --host 127.0.0.1 --port 8021 --log-level warning`,
      cwd: "../backend",
      url: "http://127.0.0.1:8021/api/health",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 3021 --strictPort",
      url: "http://127.0.0.1:3021",
      timeout: 60_000,
      reuseExistingServer: false,
      env: { FOUNDEROS_BACKEND_URL: "http://127.0.0.1:8021" },
    },
  ],
});
