import { defineConfig, devices } from "@playwright/test";

// The web port follows E2E_WEB_PORT so local dev servers the owner runs
// (e.g. the website MVP) never collide with the disposable test run.
const WEB_PORT = process.env.E2E_WEB_PORT ?? "3100";

export default defineConfig({
  testDir: "./tests",
  retries: 0,
  timeout: 30000,
  // The dashboard flows are shared journeys (register → org → bot → archive);
  // serial single-worker runs keep them deterministic.
  workers: 1,
  // Whole-run budget: web build + API boot + all specs. 240s was too small (overview.spec alone allows 240s).
  globalTimeout: 1_800_000,
  globalSetup: "./tests/e2e-api-setup.ts",
  globalTeardown: "./tests/e2e-api-teardown.ts",
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run build && npm run start -- --port " + WEB_PORT,
    url: `http://127.0.0.1:${WEB_PORT}`,
    reuseExistingServer: false,
    timeout: 180000,
  },
});
