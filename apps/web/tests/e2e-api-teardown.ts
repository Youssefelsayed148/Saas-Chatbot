/** Playwright global teardown: stop the API server spawned by the setup module. */

import type { ChildProcess } from "node:child_process";

const holder = globalThis as unknown as { __e2eServer?: ChildProcess | null };

export default async function globalTeardown(): Promise<void> {
  const server = holder.__e2eServer;
  if (server) {
    server.kill("SIGTERM");
    holder.__e2eServer = null;
    console.log("[e2e] Stopped the E2E API server.");
  }
}
