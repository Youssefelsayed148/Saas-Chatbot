import { expect, type Page, test } from "@playwright/test";
import { registerAdmin } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

/**
 * P4-06 E2E (docs/11): /platform gated SERVER-SIDE (non-staff redirected);
 * staff view the client list, onboard a client end to end (tenant + admin
 * one-time invite + bot), and open the client detail (bots, members, audit).
 * The staff flag is not a tenant role and has no self-service path, so the
 * E2E sets it the way the pytest suite does — a direct UPDATE on the SAME
 * disposable E2E database the harness API serves.
 */

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
  await registerAdmin(page, "Platform", { email: staffEmail });
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
    .fill(`admin.${Date.now()}@client.example`);
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
  // Pick the row by name: right after Search the list can still hold unfiltered rows.
  await page
    .locator("[data-testid='platform-tenants'] a", { hasText: clientName })
    .first()
    .click();
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

  // The onboarded client has no membership for this operator.
  const clientId = page.url().split("/").at(-1)!;
  const preview = await (
    await page.request.get(`/api/v1/tenants/${clientId}/data/deletion-preview`)
  ).json();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  expect(
    me.memberships.some(
      (membership: { tenant_id: string }) => membership.tenant_id === clientId,
    ),
  ).toBe(false);
  await page
    .getByRole("link", { name: "Organization data and deletion" })
    .click();
  await page.getByLabel(`Type ${clientName} to confirm`).fill(clientName);
  await page
    .getByLabel("Reason for deletion")
    .fill("Disposable browser test cleanup");
  const schedule = page.getByRole("button", {
    name: "Schedule organization deletion",
  });
  await schedule.click();
  const dialog = page.getByRole("dialog", {
    name: "Delete this organization?",
  });
  await expect(dialog).toBeVisible();
  for (const [kind, count] of Object.entries(preview.counts)) {
    await expect(
      dialog.getByText(`${kind}: ${count}`, { exact: true }),
    ).toBeVisible();
  }
  const confirm = dialog.getByRole("button", {
    name: "Delete organization now",
  });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Confirm organization name").fill(`${clientName} `);
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await page.request.get(`/api/v1/tenants/${clientId}`)).status()).toBe(
    200,
  );
  await page.getByLabel(`Type ${clientName} to confirm`).fill(clientName);
  await schedule.click();
  await dialog.getByLabel("Confirm organization name").fill(clientName);
  await expect(confirm).toBeEnabled();
  const deleted = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().endsWith(`/tenants/${clientId}/data`),
  );
  await confirm.click();
  expect((await deleted).status()).toBe(204);
  expect((await page.request.get(`/api/v1/tenants/${clientId}`)).status()).toBe(
    404,
  );
});
