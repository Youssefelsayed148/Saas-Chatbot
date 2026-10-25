import { expect, type Page, test } from "@playwright/test";
import { registerOperator } from "./e2e-helpers";

/**
 * P4-03 E2E: appearance settings are saved and reflected, the Install page
 * shows the real script snippet for the bot's own locator and the
 * sample-page helper opens the real embed (the chat flow itself is covered
 * by widget.spec.ts).
 */

async function createOrgAndBot(
  page: Page,
): Promise<{ tenantId: string; botId: string; locator: string }> {
  const { tenantId, botName } = await registerOperator(page, "Install", {});
  await page
    .getByRole("link", { name: new RegExp(`Open ${botName}`) })
    .click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  const bot = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json()) as { widget_locator: string };
  return { tenantId, botId, locator: bot.widget_locator };
}

test("activate a draft bot on Settings, then Install shows snippet + sample helper", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { tenantId, botId, locator } = await createOrgAndBot(page);

  // Draft bot: Install flags the status and offers no sample page yet.
  await page.goto(`/app/${tenantId}/bots/${botId}/install`);
  await expect(page.getByTestId("install-status")).toHaveAttribute(
    "data-status",
    "draft",
  );

  // Activate from the Settings tab (P4-01 lifecycle through the UI).
  await page.goto(`/app/${tenantId}/bots/${botId}/settings`);
  await page.getByTestId("activate-bot").click();
  await expect(page.getByText("Status:", { exact: false })).toHaveAttribute(
    "data-status",
    "active",
    { timeout: 10_000 },
  );
  await expect(page.getByTestId("settings-locator")).toHaveText(locator);

  await page.goto(`/app/${tenantId}/bots/${botId}/install`);
  await expect(page.getByTestId("install-status")).toHaveAttribute(
    "data-status",
    "active",
  );
  const snippet = page.getByTestId("install-snippet");
  await expect(snippet).toContainText("/widget/v1/loader.js");
  await expect(snippet).toContainText(`data-locator="${locator}"`);
  await expect(page.getByRole("link", { name: /sample page/ })).toBeVisible();

  // Sample-page helper: the snippet embeds the same locator.
  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=store-a`,
  );
  await expect(page.getByTestId("sample-snippet")).toContainText(locator);
  await expect(page.getByTestId("widget-bubble")).toBeVisible();

  // Appearance saved: colour + position survive a reload of Settings.
  await page.goto(`/app/${tenantId}/bots/${botId}/settings`);
  await page.getByLabel("Widget colour (hex, e.g. #1a2b3c)").fill("#123456");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible({
    timeout: 10_000,
  });
  const liveConfig = await page.request.get(
    `/api/public/v1/widgets/${locator}/config`,
  );
  expect(liveConfig.status()).toBe(200);
  expect((await liveConfig.json()).config.colour).toBe("#123456");
  await page.reload();
  await expect(
    page.getByLabel("Widget colour (hex, e.g. #1a2b3c)"),
  ).toHaveValue("#123456");
});
