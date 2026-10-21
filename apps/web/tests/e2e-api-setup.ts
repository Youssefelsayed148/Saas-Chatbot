/** Playwright global setup: boot the real FastAPI backend AND the DB worker
 * (python -m app.worker) against a disposable database. */

import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import {
  API_DIR,
  HEALTH_URL,
  disposableUrl,
  resolvePython,
  waitFor,
} from "./e2e-api-common";

interface ServerHandle {
  server: ChildProcess | null;
  databaseUrl: string;
}

export async function startServer(): Promise<ServerHandle> {
  if (await waitFor(HEALTH_URL, 1500)) {
    // Reuse is opt-in: silently testing against an unknown running server
    // (e.g. the compose stack on the dev database) hides the disposable-DB
    // guarantee and stale builds. Refuse unless explicitly requested.
    if (process.env.E2E_REUSE_API !== "1") {
      throw new Error(
        `Something is already listening on ${HEALTH_URL}. Stop the local ` +
          "compose stack (docker compose down) or point E2E_API_PORT/CHE " +
          "elsewhere, or set E2E_REUSE_API=1 to accept the existing server.",
      );
    }
    console.log(
      `[e2e] Reusing an already-running API at ${HEALTH_URL} (forced).`,
    );
    const base = process.env.TEST_DATABASE_URL ?? process.env.DATABASE_URL;
    if (!base)
      throw new Error("Set DATABASE_URL to a disposable PostgreSQL base URL.");
    return { server: null, databaseUrl: disposableUrl(base) };
  }

  const base = process.env.TEST_DATABASE_URL ?? process.env.DATABASE_URL;
  if (!base) {
    throw new Error("Set DATABASE_URL to a disposable PostgreSQL base URL.");
  }
  const databaseUrl = disposableUrl(base);
  console.log(
    `[e2e] Starting API on ${HEALTH_URL} with disposable database ${new URL(databaseUrl).pathname}.`,
  );

  const python = resolvePython();
  // Create the disposable database if missing, then run Alembic migrations (never create_all).
  spawnSync(
    python,
    [
      "-c",
      [
        "import os, psycopg, sqlalchemy",
        "u = sqlalchemy.make_url(os.environ['DATABASE_URL'])",
        "maintenance = u.set(database='postgres').render_as_string(hide_password=False)",
        "with psycopg.connect(maintenance, autocommit=True) as conn:",
        "    name = u.database",
        "    exists = conn.execute('SELECT 1 FROM pg_database WHERE datname = %s', (name,)).fetchone()",
        "    if exists is None:",
        "        safe = name.replace('\"', '')",
        "        conn.execute('CREATE DATABASE \"' + safe + '\"')",
        "print('e2e-db-ready')",
      ].join("\n"),
    ],
    {
      cwd: API_DIR,
      env: { ...process.env, DATABASE_URL: databaseUrl },
      stdio: "inherit",
    },
  );
  spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL: databaseUrl },
    stdio: "inherit",
  });

  const server = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--app-dir",
      API_DIR,
      "--host",
      "127.0.0.1",
      "--port",
      process.env.E2E_API_PORT ?? "8000",
      "--timeout-keep-alive",
      "65",
    ],
    {
      cwd: API_DIR,
      env: {
        ...process.env,
        DATABASE_URL: databaseUrl,
        ENVIRONMENT: "test",
        SELF_SERVE_SIGNUP: "true",
        // The playground E2E runs the deterministic offline stub model
        // (dev-only; production never sets this).
        CHAT_STUB_MODEL: "1",
        EMBEDDING_TEST_STUB: "1",
      },
      stdio: "inherit",
    },
  );
  const up = await waitFor(HEALTH_URL, 30000);
  if (!up) {
    throw new Error("The E2E API did not become healthy in time.");
  }
  return { server, databaseUrl };
}

/** Start the P2 worker (same codebase) on the disposable _test database. */
export function startWorker(databaseUrl: string): ChildProcess {
  const python = resolvePython();
  const worker = spawn(python, ["-m", "app.worker"], {
    cwd: API_DIR,
    env: {
      ...process.env,
      DATABASE_URL: databaseUrl,
      WORKER_ALLOW_ONLY_TEST_DB: "1",
      CHAT_STUB_MODEL: "1",
      EMBEDDING_TEST_STUB: "1",
      WORKER_HEARTBEAT_FILE: "/tmp/chatbot-e2e-worker-heartbeat",
    },
    stdio: "inherit",
  });
  console.log("[e2e] Started the DB worker (python -m app.worker).");
  return worker;
}

export default async function globalSetup(): Promise<void> {
  const handle = await startServer();
  // Make the exact API database URL available to Playwright worker processes.
  process.env.E2E_DATABASE_URL = handle.databaseUrl;
  if (handle.server !== null) {
    // Only spawn a worker we own the API/database for (reuse runs keep theirs).
    const worker = startWorker(handle.databaseUrl);
    (globalThis as unknown as { __e2eWorker?: unknown }).__e2eWorker = worker;
  }
  // Share the child process with the teardown module through globalThis.
  (globalThis as unknown as { __e2eServer?: unknown }).__e2eServer =
    handle.server;
}
