import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// npm test runs inside apps/web; find the repository root by walking upward.
let probe = process.cwd();
while (
  probe !== path.parse(probe).root &&
  !existsSync(path.join(probe, "README_START_HERE.md"))
) {
  probe = path.dirname(probe);
}
export const WEB_DIR = process.cwd();
export const REPO_ROOT = probe;
export const API_DIR = path.join(REPO_ROOT, "apps", "api");

export const API_PORT = process.env.E2E_API_PORT ?? "8000";
export const HEALTH_URL = `http://127.0.0.1:${API_PORT}/health`;

export interface ServerHandle {
  server: ReturnType<typeof spawn> | null;
}

/** Force a disposable `_test` database name derived from the development URL. */
export function disposableUrl(base: string): string {
  const url = new URL(base.replace(/^postgresql\+[^:]+:/, "postgresql:"));
  let name = url.pathname.replace(/^\//, "");
  if (name.endsWith("_e2e")) {
    name = `${name}_test`;
  } else if (!name.endsWith("_test")) {
    name = `${name}_e2e_test`;
  }
  if (!name.endsWith("_test")) {
    throw new Error(`Refusing non-disposable E2E database name: ${name}`);
  }
  url.pathname = `/${name}`;
  return url.toString();
}

function pythonCandidates(): string[] {
  const venvWin = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const venvUnix = path.join(REPO_ROOT, ".venv", "bin", "python");
  return [
    process.env.E2E_PYTHON ?? "",
    venvWin,
    venvUnix,
    "python",
    "python3",
  ].filter((candidate) => candidate.length > 0);
}

export function resolvePython(): string {
  for (const candidate of pythonCandidates()) {
    try {
      const probe = spawnSync(candidate, ["-c", "print(1)"], {
        stdio: "ignore",
      });
      if (probe.status === 0) return candidate;
    } catch {
      // try next candidate
    }
  }
  throw new Error("No Python interpreter found for the E2E API server.");
}

export async function waitFor(
  url: string,
  timeoutMs: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return true;
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}
