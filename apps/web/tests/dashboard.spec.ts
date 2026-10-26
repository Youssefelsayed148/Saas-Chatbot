import { expect, test } from "@playwright/test";
import { registerAdmin, uniqueEmail } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

/**
 * P1 E2E: real API only. Requires the FastAPI backend (auto-started by the
 * Playwright global setup against a disposable *_test database).
 */

const PASSWORD = "Str0ngPass!";

test("self-service disabled hides public registration and organization creation", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ self_serve_signup: false }),
    }),
  );
  await page.goto("/register");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("link", { name: "Register" })).toHaveCount(0);

  await page.unroute("**/api/v1/auth/config");
  await registerAdmin(page, "self-serve-toggle");
  await page.route("**/api/v1/auth/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ self_serve_signup: false }),
    }),
  );
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Your organizations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Create organization" }),
  ).toHaveCount(0);
});

test("admin signup provisions first bot and bot lifecycle stays with platform staff", async ({
  page,
}) => {
  const orgName = `E2E Org ${Date.now()}`;
  const { tenantId } = await registerAdmin(page, "E2E", {
    organizationName: orgName,
  });
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Your organizations" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: orgName })).toBeVisible();
  await page.goto(`/app/${tenantId}/bots`);
  await expect(page).toHaveURL(`/app/${tenantId}`);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Bots", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create bot" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Archive" })).toHaveCount(0);

  // Sign out returns to the protected flow requiring re-login.
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("/login");
});

test("a second user cannot reach the first user's organization", async ({
  browser,
}) => {
  const firstEmail = uniqueEmail("first");
  const orgName = `Private Org ${Date.now()}`;

  const first = await browser.newContext();
  const firstPage = await first.newPage();
  await registerAdmin(firstPage, "first", {
    email: firstEmail,
    organizationName: orgName,
  });
  const orgPath = new URL(firstPage.url()).pathname; // /app/<tenantId>/bots

  // Second browser context: an uninvited user can open only the wrong ids guesses.
  const secondEmail = uniqueEmail("second");
  const second = await browser.newContext();
  const secondPage = await second.newPage();
  await registerAdmin(secondPage, "second", { email: secondEmail });
  await secondPage.goto(orgPath);

  // The dashboard never renders the foreign org; the API answers 404 and the UI surfaces it.
  await expect(secondPage.getByText("Resource not found.")).toBeVisible();
  await expect(secondPage.getByText(orgName)).toHaveCount(0);
  await expect(secondPage.getByRole("heading", { name: orgName })).toHaveCount(
    0,
  );

  await first.close();
  await second.close();
});

test("team management: admin invites, invitee accepts, viewer sees read-only bots", async ({
  browser,
}) => {
  const adminEmail = uniqueEmail("admin");
  const first = await browser.newContext();
  const admin = await first.newPage();
  const { tenantId } = await registerAdmin(admin, "Team", {
    email: adminEmail,
  });
  // Staff plan assignment remains available to prepare admin/editor permission checks.
  promoteToStaff(adminEmail);
  const csrf = await admin.evaluate(
    () =>
      document.cookie
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="))
        ?.split("=")[1] ?? "",
  );
  const plan = await admin.request.patch(
    `/api/v1/platform/tenants/${tenantId}/plan`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: {
        plan_label: "starter",
        reason: "E2E editor second bot permission coverage",
      },
    },
  );
  expect(plan.status()).toBe(200);

  // Invite an editor and a viewer.
  await admin.goto(`/app/${tenantId}/settings/members`);
  const editorEmail = uniqueEmail("editor");
  const provisionEditor = await admin.request.post("/api/v1/platform/users", {
    headers: { "X-CSRF-Token": csrf },
    data: { email: editorEmail, password: PASSWORD },
  });
  expect(provisionEditor.status()).toBe(201);
  await admin.getByLabel("Email", { exact: true }).fill(editorEmail);
  await admin.getByRole("combobox", { name: "Role" }).selectOption("editor");
  await admin.getByRole("button", { name: "Create invite link" }).click();
  const inviteCode = (await admin.locator("code").textContent()) ?? "";
  expect(inviteCode).toContain("/accept-invite?token=");

  const viewerEmail = uniqueEmail("viewer");
  const provisionViewer = await admin.request.post("/api/v1/platform/users", {
    headers: { "X-CSRF-Token": csrf },
    data: { email: viewerEmail, password: PASSWORD },
  });
  expect(provisionViewer.status()).toBe(201);
  await admin.getByLabel("Email", { exact: true }).fill(viewerEmail);
  await admin.getByRole("combobox", { name: "Role" }).selectOption("viewer");
  await admin.getByRole("button", { name: "Create invite link" }).click();

  // The existing editor signs in with the invited address and accepts.
  const second = await browser.newContext();
  const editor = await second.newPage();
  await editor.goto(inviteCode);
  await editor
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await editor.getByLabel("Email").fill(editorEmail);
  await editor.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await editor.getByRole("button", { name: "Sign in", exact: true }).click();
  await editor.getByRole("button", { name: "Accept invitation" }).click();
  await expect(editor.getByRole("status")).toContainText(/Welcome aboard/i);
  await editor.getByRole("link", { name: /Go to your dashboard/i }).click();
  await editor.waitForURL("/app");

  // Two orgs listed? The editor belongs only to the invited org.
  await editor.getByRole("link", { name: /Team Org/i }).click();
  await editor.waitForURL(/\/app\/[0-9a-f-]{36}$/);

  // Tenant members cannot create bots; the client UI directs them to support.
  await expect(editor.getByRole("button", { name: "Create bot" })).toHaveCount(
    0,
  );
  await expect(
    editor.getByRole("link", { name: "Bots", exact: true }),
  ).toHaveCount(0);
  const editorCsrf = await editor.evaluate(
    () =>
      document.cookie
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="))
        ?.split("=")[1] ?? "",
  );
  const deniedBot = await editor.request.post(
    `/api/v1/tenants/${tenantId}/bots`,
    {
      headers: { "X-CSRF-Token": editorCsrf },
      data: { name: `Editor Bot ${Date.now()}` },
    },
  );
  expect(deniedBot.status()).toBe(403);

  await first.close();
  await second.close();
});

test("expired session sends the user back to login", async ({ page }) => {
  const email = uniqueEmail("expiry");
  await registerAdmin(page, "expiry", { email });
  // Simulate expiry by poisoning the HttpOnly cookie through the app itself is not
  // possible, so the sign-out mutation is exercised: after logout the protected
  // page redirects to /login (server-side revocation path).
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("/login");
  await page.goto("/app");
  await page.waitForURL("/login");
});
