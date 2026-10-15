import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// Run only after final gates. Reuse the completed build; no extra production build.
export default defineConfig({
  ...base,
  testDir: "./screenshots",
  webServer: {
    command: "npm run start -- --port 3100",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
