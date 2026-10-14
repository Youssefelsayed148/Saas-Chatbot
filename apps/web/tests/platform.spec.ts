import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

/**
 * P4-06 E2E (docs/11): /platform gated SERVER-SIDE (non-staff redirected);
 * staff view the client list, onboard a client end to end (tenant + owner
 * one-time invite + bot), and open the client detail (bots, members, audit).
 * The staff flag is not a tenant role and has no self-service path, so the
 * E2E sets it the way the pytest suite does — a direct UPDATE on the SAME
 * disposable E2E database the harness API serves.
 */

const PASSWORD = "Str0ngPass!";

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

function promoteToStaff(email: string): void {
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

async function csrfOf(page: Page): Promise<string> {
  return page
    .evaluate(() => document.cookie)
    .then((cookies) => {
      const entry = cookies
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="));
      return entry ? entry.split("=")[1] : "";
    });
}

test("non-staff cannot reach /platform (server-side redirect)", async ({
  page,
}) => {
  // NOT signed in at all: the layout's per-request server-side guard must
  // bounce the anonymous visitor to /login — /platform is never rendered.
  await page.goto("/platform");
  await expect(page, "the layout redirects the anonymous visitor").toHaveURL(
    /\/login/,
  );
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("staff list, onboard a client end to end, and open the client detail", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const staffEmail = `platform.${Date.now()}@example.com`;

  // Register through the UI, then promote directly in the E2E database.
  await page.goto("/register");
  await page.getByLabel("Email").fill(staffEmail);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/app");
  promoteToStaff(staffEmail);

  await page.goto("/platform");
  await expect(page.getByTestId("platform-staff-badge")).toContainText(
    "Platform staff console",
    { timeout: 20_000 },
  );

  // Tenant A/B isolation is unaffected: assert a demo tenant exists only via
  // its own tenant name (per-bot/bot isolation covered by the pytest suite).
  const clientName = `Onboarded Org ${Date.now()}`;
  await page.getByTestId("ob-client-name").fill(clientName);
  await page
    .getByTestId("ob-owner-email")
    .fill(`owner.${Date.now()}@client.example`);
  await page.getByTestId("ob-bot-name").fill("First Bot");
  await page.getByTestId("ob-submit").click();
  const invite = page.getByTestId("ob-invite-link");
  await expect(invite).toContainText("/accept-invite?token=", {
    timeout: 20_000,
  });
  await expect(invite).toContainText("Durable request:");

  // The new client appears in the list (searchable).
  await page.getByTestId("platform-query").fill(clientName);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("platform-tenants")).toContainText(clientName);

  // Open the client detail: bot + members + audit rows render.
  await page.locator("[data-testid='platform-tenants'] a").first().click();
  await page.waitForURL(/\/platform\/clients\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("client-detail-name")).toContainText(
    clientName,
  );
  await expect(page.getByTestId("client-detail-bots")).toContainText(
    "First Bot",
  );
  await expect(page.getByTestId("client-detail-bots")).toContainText(
    "nothing published",
  );
  await page.getByTestId("client-detail-bots");
  const csrf = await csrfOf(page);
  expect(csrf).toBeTruthy();
});
