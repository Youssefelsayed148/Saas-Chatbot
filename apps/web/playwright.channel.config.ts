import { defineConfig, devices } from "@playwright/test";

// UI contract tests mock every API request; no database, worker or Many network.
export default defineConfig({
  testDir: "./tests",
  testMatch: "channel-delivery.spec.ts",
  workers: 1,
  timeout: 30000,
  globalTimeout: 600000,
  use: { baseURL: "http://127.0.0.1:3101", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run build && npm run start -- --port 3101",
    url: "http://127.0.0.1:3101",
    reuseExistingServer: false,
    timeout: 180000,
  },
});
