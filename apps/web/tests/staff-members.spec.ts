import { expect, test, type Page } from "@playwright/test";
import { registerOperator, uniqueEmail } from "./e2e-helpers";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("staff creates, resets, deactivates and manages existing-user invitations", async ({
  page,
  browser,
}) => {
  test.setTimeout(180_000);
  const { tenantId } = await registerOperator(page, "staff-members");
  const email = uniqueEmail("created-member");
  await page.goto("/platform/members");
  const create = page.getByRole("region", { name: "Create user", exact: true });
  await create.getByLabel("Email", { exact: true }).fill(email);
  await create.getByRole("button", { name: "Generate password" }).click();
  await create
    .getByRole("combobox", { name: "Organization" })
    .selectOption(tenantId);
  await create
    .getByRole("button", { name: "Create user", exact: true })
    .click();
  const password = await page.getByTestId("issued-password").innerText();
  // The directory is oldest-first with 25 per page; filter to the new user so
  // their link is on the first page even with accumulated fixture users.
  await page.getByLabel("Search email").fill(email);
  await expect(
    page.getByRole("link", { name: email, exact: true }),
  ).toBeVisible();
  const context = await browser.newContext();
  const member = await context.newPage();
  try {
    await login(member, email, password);
    await expect(member).toHaveURL(/\/app/);
    await page.getByRole("link", { name: email, exact: true }).click();
    const reset = page.getByRole("region", {
      name: "Reset password",
      exact: true,
    });
    await reset.getByRole("button", { name: "Generate password" }).click();
    await reset
      .getByRole("button", { name: "Reset password", exact: true })
      .click();
    const nextPassword = await page.getByTestId("issued-password").innerText();
    await login(member, email, nextPassword);
    await expect(member).toHaveURL(/\/app/);
    await page
      .getByRole("button", { name: "Deactivate user", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(page.getByText("Inactive", { exact: true })).toBeVisible();
    await login(member, email, nextPassword);
    await expect(member.getByRole("alert")).toBeVisible();
    await page
      .getByRole("button", { name: "Reactivate user", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(page.getByText("Active", { exact: true })).toBeVisible();
    await login(member, email, nextPassword);
    await expect(member).toHaveURL(/\/app/);
    await page.goto(`/platform/clients/${tenantId}`);
    await page.getByRole("tab", { name: "Members", exact: true }).click();
    const row = page.getByRole("row").filter({ hasText: email });
    await row.getByRole("button", { name: "Remove membership" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(row).toHaveCount(0);
    const manage = page.getByRole("region", {
      name: "Manage organization members",
    });
    await manage.getByLabel("Search email").fill(email);
    await manage.getByRole("button", { name: "Search users" }).click();
    await manage
      .getByRole("combobox", { name: "Existing user" })
      .selectOption({ label: email });
    await manage
      .getByRole("button", { name: "Add existing user", exact: true })
      .click();
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Remove membership" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(row).toHaveCount(0);
    await manage
      .getByRole("button", { name: "Invite existing user", exact: true })
      .click();
    const invitation = await manage.locator("code").innerText();
    // Removing the only membership refuses login until acceptance, so reuse
    // the session acquired before removal rather than logging in again.
    await member.goto(invitation);
    await member.getByRole("button", { name: /accept invitation/i }).click();
    await expect(member.getByRole("status")).toContainText("You joined");
  } finally {
    await context.close();
  }
});

test("non-staff cannot access the Members list or details", async ({
  page,
}) => {
  await page.goto("/platform/members");
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/platform/members/11111111-1111-4111-8111-111111111111");
  await expect(page).toHaveURL(/\/login/);
});
