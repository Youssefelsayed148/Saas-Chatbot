import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  retries: 0,
  timeout: 30000,
  globalTimeout: 240000,
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run build && npm run start -- --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 180000,
  },
});
