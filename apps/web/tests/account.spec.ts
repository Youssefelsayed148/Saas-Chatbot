/**
 * S4: the Account page and password change, from both shells.
 *
 * Scenarios: change password then sign in with the new one in a clean
 * context; a second signed-in context is signed out; the staff account page
 * works (platform shell); wrong current password shows the safe error;
 * anonymous visitors are redirected to /login.
 */

import { expect, type Page, test } from "@playwright/test";

import { registerAdmin, registerOperator, uniqueEmail } from "./e2e-helpers";

const OLD_PASSWORD = "Str0ngPass!";
const NEW_PASSWORD = "Br4ndNewPass!";

async function openAccount(page: Page) {
  await page.getByRole("link", { name: "Account" }).click();
  await page.waitForURL(/\/account$/);
}

test.describe("Account page (S4)", () => {
  test("anonymous visitors are redirected to /login", async ({ page }) => {
    await page.goto("/account");
    await expect(page).toHaveURL(/\/login/);
  });

  test("client user changes password; other session is signed out; new password works", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const email = uniqueEmail("acct-client");
    await registerAdmin(page, "AcctClient", { email });

    // A second signed-in context shares the account.
    const secondContext = await browser.newContext();
    const secondPage = await secondContext.newPage();
    await secondPage.goto("/login");
    await secondPage.getByLabel("Email").fill(email);
    await secondPage.getByLabel("Password", { exact: true }).fill(OLD_PASSWORD);
    await secondPage.getByRole("button", { name: "Sign in" }).click();
    await secondPage.waitForURL(/\/app/);

    await openAccount(page);
    await expect(page.getByTestId("account-email")).toHaveText(
      `Signed in as ${email}`,
    );
    await expect(page.getByTestId("workspace-context")).not.toHaveText(
      "Platform admin",
    );

    await page.getByLabel("Current password").fill(OLD_PASSWORD);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByTestId("account-success")).toBeVisible();

    // The second signed-in context is signed out by the change.
    await secondPage.goto("/app");
    await expect(secondPage).toHaveURL(/\/login/);
    await secondContext.close();

    // A clean context signs in with the NEW password (old one is dead).
    const clean = await browser.newContext();
    const cleanPage = await clean.newPage();
    await cleanPage.goto("/login");
    await cleanPage.getByLabel("Email").fill(email);
    await cleanPage.getByLabel("Password", { exact: true }).fill(OLD_PASSWORD);
    await cleanPage.getByRole("button", { name: "Sign in" }).click();
    await expect(
      cleanPage.getByRole("alert").filter({ hasText: "incorrect" }),
    ).toBeVisible();
    await cleanPage.getByLabel("Password", { exact: true }).fill(NEW_PASSWORD);
    await cleanPage.getByRole("button", { name: "Sign in" }).click();
    await cleanPage.waitForURL(/\/app/);
    await clean.close();

    await context.close();
  });

  test("wrong current password shows the safe error and keeps the session", async ({
    page,
  }) => {
    const email = uniqueEmail("acct-wrong");
    await registerAdmin(page, "AcctWrong", { email });
    await openAccount(page);

    await page.getByLabel("Current password").fill("NotTheCurrent1!");
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Change password" }).click();

    await expect(page.getByTestId("account-error")).toHaveText(
      "Current password is incorrect.",
    );
    // Still signed in on the account page.
    await expect(page.getByTestId("account-email")).toHaveText(
      `Signed in as ${email}`,
    );
    await expect(page.getByTestId("account-success")).toHaveCount(0);
  });

  test("platform staff see the account page in the platform shell and can change their password", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const email = uniqueEmail("acct-staff");
    await registerOperator(page, "AcctStaff", { email });

    await page.goto("/platform");
    await openAccount(page);
    await expect(page.getByTestId("account-email")).toHaveText(
      `Signed in as ${email}`,
    );
    // The platform shell context badge is shown on the account page.
    await expect(page.getByTestId("workspace-context")).toHaveText(
      "Platform admin",
    );

    await page.getByLabel("Current password").fill(OLD_PASSWORD);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByTestId("account-success")).toBeVisible();

    // The staff session was rotated, not dropped: navigation still works.
    await page.goto("/platform");
    await expect(page).toHaveURL(/\/platform/);
    await context.close();
  });

  test("client-side checks block mismatched confirmation", async ({ page }) => {
    const email = uniqueEmail("acct-mismatch");
    await registerAdmin(page, "AcctMismatch", { email });
    await openAccount(page);
    await page.getByLabel("Current password").fill(OLD_PASSWORD);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password").fill("Different9!");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByTestId("account-error")).toHaveText(
      "New password and confirmation do not match.",
    );
  });
});
