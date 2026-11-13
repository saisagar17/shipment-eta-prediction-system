import { defineConfig } from "@playwright/test";
const runningApp = process.env.SHIPMENT_E2E_BASE_URL;
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: runningApp || "http://127.0.0.1:5184",
    channel: process.env.BROWSER_CHANNEL,
    viewport: { width: 1440, height: 980 },
    reducedMotion: "reduce",
  },
  webServer: runningApp ? undefined : [
    {
      command: "python -m uvicorn backend.main:app --app-dir src --host 127.0.0.1 --port 8014",
      cwd: "..",
      url: "http://127.0.0.1:8014/api/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 5184 --strictPort",
      env: { SHIPMENT_API_ORIGIN: "http://127.0.0.1:8014" },
      url: "http://127.0.0.1:5184",
      reuseExistingServer: false,
    },
  ],
});
