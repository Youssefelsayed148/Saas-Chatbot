import { expect, test } from "@playwright/test";
test("foundation renders with no browser errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle("Welcome · Website Chatbot SaaS");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Application foundation",
  );
  expect(errors).toEqual([]);
});
