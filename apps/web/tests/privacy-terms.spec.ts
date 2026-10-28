import { expect, test } from "@playwright/test";

for (const [path, heading, otherPath] of [
  ["/privacy", "Privacy notice", "/terms"],
  ["/terms", "Terms of use", "/privacy"],
]) {
  test(`${path} is publicly readable without a staff session`, async ({
    page,
  }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(path);
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
    await expect(page.getByRole("main")).toContainText("ManyOsirisChat");
    await expect(page.getByRole("link")).toHaveAttribute("href", otherPath);
  });
}
