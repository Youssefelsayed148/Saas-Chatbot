/** Playwright global teardown: stop the API server and the worker spawned by
 * the setup module. */

import type { ChildProcess } from "node:child_process";

interface Holder {
  __e2eServer?: ChildProcess | null;
  __e2eWorker?: ChildProcess | null;
}

const holder = globalThis as unknown as Holder;

export default async function globalTeardown(): Promise<void> {
  const server = holder.__e2eServer;
  if (server) {
    server.kill("SIGTERM");
    holder.__e2eServer = null;
    console.log("[e2e] Stopped the E2E API server.");
  }
  const worker = holder.__e2eWorker;
  if (worker) {
    worker.kill("SIGTERM");
    holder.__e2eWorker = null;
    console.log("[e2e] Stopped the E2E worker.");
  }
}
