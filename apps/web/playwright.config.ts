import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  retries: 0,
  timeout: 30000,
  // The dashboard flows are shared journeys (register → org → bot → archive);
  // serial single-worker runs keep them deterministic.
  workers: 1,
  globalTimeout: 240000,
  globalSetup: "./tests/e2e-api-setup.ts",
  globalTeardown: "./tests/e2e-api-teardown.ts",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run build && npm run start -- --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 180000,
  },
});
