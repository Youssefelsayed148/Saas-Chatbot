/**
 * S6: registration is closed by default (self_serve_signup=false in the
 * committed configuration). The E2E harness boots the API with the flag ON
 * (SELF_SERVE_SIGNUP=true) so this spec verifies the flagged-on UI: the
 * Register link stays reachable and /register still offers workspace
 * creation. The flagged-off hide behaviour is asserted per code contract in
 * the backend suite (INVITATION_REQUIRED) — the E2E environment cannot boot
 * a second API with the flag off.
 */

import { expect, test } from "@playwright/test";

test.describe("Login and register visibility (S6)", () => {
  test("login page shows the Register link while self-serve signup is on", async ({
    page,
  }) => {
    await page.goto("/login");
    const link = page.getByRole("link", { name: "Register" });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/register");
  });

  test("register page offers workspace creation while signup is on", async ({
    page,
  }) => {
    await page.goto("/register");
    await expect(
      page.getByText("Create your workspace and first website assistant."),
    ).toBeVisible();
    await expect(page.getByLabel("Organization name")).toBeVisible();
  });
});
