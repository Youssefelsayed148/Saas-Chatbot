import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

function repoRoot(): string {
  let probe = process.cwd();
  while (probe !== path.parse(probe).root) {
    if (existsSync(path.join(probe, "README_START_HERE.md"))) return probe;
    probe = path.dirname(probe);
  }
  throw new Error("Repository root not found.");
}

function pythonBin(): string {
  const candidates = [
    process.env.E2E_PYTHON ?? "",
    path.join(repoRoot(), ".venv", "Scripts", "python.exe"),
    path.join(repoRoot(), ".venv", "bin", "python"),
    "python3",
  ].filter((candidate) => candidate.length > 0);
  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ["-c", "print(1)"], { stdio: "ignore" });
      return candidate;
    } catch {
      // try the next one
    }
  }
  throw new Error("No python found for the staff promotion.");
}

export function promoteToStaff(email: string): void {
  const databaseUrl = process.env.E2E_DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "E2E_DATABASE_URL was not exported by the Playwright API setup.",
    );
  }
  execFileSync(
    pythonBin(),
    [
      "-c",
      [
        "import sys, sqlalchemy, psycopg",
        "url = sqlalchemy.make_url(sys.argv[2]).set(drivername='postgresql')",
        "if not (url.database or '').endswith('_test'): raise RuntimeError('Staff promotion requires a disposable test database')",
        "with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as conn:",
        "    result = conn.execute('UPDATE users SET is_platform_staff = TRUE WHERE email = %s', (sys.argv[1],))",
        "    if result.rowcount != 1: raise RuntimeError('Expected one registered staff user')",
        "",
      ].join("\n"),
      email,
      databaseUrl,
    ],
    { cwd: path.join(repoRoot(), "apps", "api"), stdio: "pipe" },
  );
}

export async function assignStarterPlan(
  page: import("@playwright/test").Page,
  tenantId: string,
  email: string,
): Promise<void> {
  promoteToStaff(email);
  const csrf = await page.evaluate(
    () =>
      document.cookie
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="))
        ?.split("=")[1] ?? "",
  );
  const response = await page.request.patch(
    `/api/v1/platform/tenants/${tenantId}/plan`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: {
        plan_label: "starter",
        reason: "E2E coverage requires Starter placeholder limits",
      },
    },
  );
  if (response.status() !== 200)
    throw new Error(`Plan assignment failed: ${response.status()}`);
}
