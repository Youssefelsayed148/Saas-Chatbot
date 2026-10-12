/** Playwright global setup: boot the real FastAPI backend AND the DB worker
 * (python -m app.worker) against a disposable database. */

import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import {
  API_DIR,
  HEALTH_URL,
  disposableUrl,
  readEnvFile,
  resolvePython,
  waitFor,
} from "./e2e-api-common";

interface ServerHandle {
  server: ChildProcess | null;
  databaseUrl: string;
}

export async function startServer(): Promise<ServerHandle> {
  if (await waitFor(HEALTH_URL, 1500)) {
    console.log(`[e2e] Reusing an already-running API at ${HEALTH_URL}.`);
    const base = process.env.DATABASE_URL ?? readEnvFile().DATABASE_URL;
    return { server: null, databaseUrl: disposableUrl(base ?? "") };
  }

  const base = process.env.DATABASE_URL ?? readEnvFile().DATABASE_URL;
  if (!base) {
    throw new Error(
      "No DATABASE_URL found for the E2E backend (env or repository .env).",
    );
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
    ],
    {
      cwd: API_DIR,
      env: { ...process.env, DATABASE_URL: databaseUrl },
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
      WORKER_HEARTBEAT_FILE: "/tmp/chatbot-e2e-worker-heartbeat",
    },
    stdio: "inherit",
  });
  console.log("[e2e] Started the DB worker (python -m app.worker).");
  return worker;
}

export default async function globalSetup(): Promise<void> {
  const handle = await startServer();
  if (handle.server !== null) {
    // Only spawn a worker we own the API/database for (reuse runs keep theirs).
    const worker = startWorker(handle.databaseUrl);
    (globalThis as unknown as { __e2eWorker?: unknown }).__e2eWorker = worker;
  }
  // Share the child process with the teardown module through globalThis.
  (globalThis as unknown as { __e2eServer?: unknown }).__e2eServer =
    handle.server;
}
