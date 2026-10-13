import { expect, type Page, test } from "@playwright/test";

/**
 * P4-03 E2E: appearance settings are saved and reflected, the Install page
 * shows the real script snippet for the bot's own locator and the
 * sample-page helper opens the real embed (the chat flow itself is covered
 * by widget.spec.ts).
 */

const PASSWORD = "Str0ngPass!";

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

async function registerUser(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/app");
}

async function createOrgAndBot(
  page: Page,
): Promise<{ tenantId: string; botId: string; locator: string }> {
  await page.getByLabel("Name").fill(`Install Org ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  const tenantId = new URL(page.url()).pathname.split("/")[2];
  const botName = `Install Bot ${Date.now()}`;
  await page.getByLabel("Bot name").fill(botName);
  await page.getByRole("button", { name: "Create bot" }).click();
  await page
    .getByRole("row", { name: new RegExp(botName) })
    .getByRole("link")
    .first()
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
  await registerUser(page, uniqueEmail("installer"));
  const { tenantId, botId, locator } = await createOrgAndBot(page);

  // Draft bot: Install flags the status and offers no sample page yet.
  await page.goto(`/app/${tenantId}/bots/${botId}/install`);
  await expect(page.getByTestId("install-status")).toContainText("draft");

  // Activate from the Settings tab (P4-01 lifecycle through the UI).
  await page.goto(`/app/${tenantId}/bots/${botId}/settings`);
  await page.getByTestId("activate-bot").click();
  await expect(page.getByText("Status:", { exact: false })).toContainText(
    "active",
    { timeout: 10_000 },
  );
  await expect(page.getByTestId("settings-locator")).toHaveText(locator);

  await page.goto(`/app/${tenantId}/bots/${botId}/install`);
  await expect(page.getByTestId("install-status")).toContainText("active");
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
  await page.reload();
  await expect(
    page.getByLabel("Widget colour (hex, e.g. #1a2b3c)"),
  ).toHaveValue("#123456");
});
