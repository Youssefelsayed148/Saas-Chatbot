import { expect, test } from "@playwright/test";
import { registerOwner } from "./e2e-helpers";

test("tenant Overview reads existing data and keeps Bots as the signup destination", async ({page}) => {
  const {tenantId} = await registerOwner(page, "Overview route");
  await expect(page).toHaveURL(`/app/${tenantId}/bots`);
  const writes: string[] = [];
  page.on("request", request => {if (["POST", "PATCH", "DELETE"].includes(request.method())) writes.push(request.url());});
  await page.goto(`/app/${tenantId}`);
  await expect(page.getByRole("heading", {name: "Overview", exact: true})).toBeVisible();
  await expect(page.getByText("First bot created", {exact: true})).toBeVisible();
  await expect(page.getByText(/final pricing and limits are TBD/)).toBeVisible();
  expect(writes).toEqual([]);
});

test("workspace theme persists and keyboard palette only navigates", async ({
  page,
}) => {
  const { tenantId } = await registerOwner(page, "Shell");
  await expect(page.getByTestId("workspace-context")).toContainText("owner");
  const before = await page.locator("html").getAttribute("data-theme");
  await page.getByTestId("theme-toggle").first().click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    before === "dark" ? "light" : "dark",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    before === "dark" ? "light" : "dark",
  );
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Go to a page" });
  await expect(palette).toBeVisible();
  await palette.getByLabel("Search pages", { exact: true }).fill("Inbox");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/app/${tenantId}/inbox`);
  await expect(palette).not.toBeVisible();
});

test("mobile navigation opens and dismisses with Escape", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await registerOwner(page, "Mobile");
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", {
    name: "Workspace navigation",
    exact: true,
  });
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
