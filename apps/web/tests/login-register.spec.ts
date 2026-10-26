/**
 * UI polish B2 (ADR-021 / ADR-022): registration is closed in the UI. There is
 * no Register link on / or /login, /register forwards to /login (keeping a safe
 * `next`), and the login screen has inline errors, a password toggle and the
 * "contact your administrator" hint (no email reset).
 */

import { expect, test } from "@playwright/test";

test.describe("Landing, login and register redirect", () => {
  test("landing shows the product and a Sign in button, no Register", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Website Chatbot",
    );
    await expect(page.getByText("Application foundation")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Register" })).toHaveCount(0);
    const signIn = page.getByRole("link", { name: "Sign in" });
    await expect(signIn).toBeVisible();
    await expect(signIn).toHaveAttribute("href", "/login");
  });

  test("login page has no Register link and shows the admin hint", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(page.getByRole("link", { name: "Register" })).toHaveCount(0);
    await expect(
      page.getByText("Forgot your password? Contact your administrator."),
    ).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  });

  test("login shows inline field errors for an empty submit", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Enter your email address.")).toBeVisible();
    await expect(page.getByText("Enter your password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("password field toggles visibility", async ({ page }) => {
    await page.goto("/login");
    const password = page.getByLabel("Password", { exact: true });
    await password.fill("Str0ngPass!");
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(password).toHaveAttribute("type", "text");
    await page.getByRole("button", { name: "Hide password" }).click();
    await expect(password).toHaveAttribute("type", "password");
  });

  test("/register redirects to /login", async ({ page }) => {
    await page.goto("/register");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("/register keeps a safe next parameter", async ({ page }) => {
    await page.goto("/register?next=%2Faccept-invite%3Ftoken%3Dabc");
    await expect(page).toHaveURL(
      /\/login\?next=%2Faccept-invite%3Ftoken%3Dabc$/,
    );
  });

  test("/register drops an unsafe next parameter", async ({ page }) => {
    await page.goto("/register?next=%2F%2Fevil.example.com");
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/register?next=https%3A%2F%2Fevil.example.com");
    await expect(page).toHaveURL(/\/login$/);
  });
});
