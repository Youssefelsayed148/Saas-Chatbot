import { expect, type Page, test } from "@playwright/test";

/**
 * P4-02/P4-03 E2E (docs/09): two TEST SITES embedding a DIFFERENT tenant's
 * bot each via the real script snippet; each widget answers strictly from its
 * own tenant's published knowledge. The two "sites" are the sample-page
 * helper (/widget/sample?locator=…&site=store-a|store-b) — on a loopback-only
 * test deployment Chrome's Local-Network-Access blocks cross-origin script
 * loads into 127.0.0.1, so cross-origin embedding is exercised by real
 * customer sites in production (no private-network boundary exists there);
 * cross-tenant isolation of sessions/messages is asserted at the API level in
 * tests/test_widget_public.py.
 */

const PASSWORD = "Str0ngPass!";

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

const mdFor = (name: string, hours: string) =>
  `---\ntitle: ${name} hours\nsource_url: https://${name}.example.com/hours\nlanguage: en\n---\n\n# ${name} opening hours\n\n${name} opens at ${hours} every day.\n`;

async function csrfToken(page: Page): Promise<string> {
  return page
    .evaluate(() => document.cookie)
    .then((cookies) => {
      const entry = cookies
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="));
      return entry ? entry.split("=")[1] : "";
    });
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
  botName: string,
): Promise<{ tenantId: string; botId: string; locator: string }> {
  await page.getByLabel("Name").fill(`Widget Org ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  const tenantId = new URL(page.url()).pathname.split("/")[2];
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
  expect(
    bot.widget_locator,
    "P4-01 assigns an opaque public locator",
  ).toBeTruthy();
  return { tenantId, botId, locator: bot.widget_locator };
}

async function publishKnowledge(
  page: Page,
  tenantId: string,
  botId: string,
  content: string,
): Promise<void> {
  const csrf = await csrfToken(page);
  const upload = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/sources/files`,
    {
      headers: { "X-CSRF-Token": csrf },
      multipart: {
        files: {
          name: "hours.md",
          mimeType: "text/markdown",
          buffer: Buffer.from(content, "utf-8"),
        },
      },
    },
  );
  expect(upload.status()).toBe(201);
  const start = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/ingestion`,
    { headers: { "X-CSRF-Token": csrf }, data: {} },
  );
  expect([201, 202]).toContain(start.status());
  let status = "";
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const jobs = await page.request.get(
      `/api/v1/tenants/${tenantId}/bots/${botId}/jobs`,
    );
    const list = (await jobs.json()) as { status: string }[];
    status = list[0]?.status ?? "missing";
    if (status === "succeeded" || status === "failed") break;
    await page.waitForTimeout(500);
  }
  expect(status, "ingest job must succeed").toBe("succeeded");
  const revisions = (await (
    await page.request.get(
      `/api/v1/tenants/${tenantId}/bots/${botId}/revisions`,
    )
  ).json()) as { revisions: { id: string; status: string }[] };
  const draft = revisions.revisions.find((row) => row.status === "draft");
  const publish = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/revisions/${String(draft?.id)}/publish`,
    { headers: { "X-CSRF-Token": csrf } },
  );
  expect(publish.status()).toBe(200);
}

/** Activate the bot through the P4-01 lifecycle transition (draft→active). */
async function activateBot(
  page: Page,
  tenantId: string,
  botId: string,
): Promise<void> {
  const csrf = await csrfToken(page);
  const response = await page.request.patch(
    `/api/v1/tenants/${tenantId}/bots/${botId}`,
    { headers: { "X-CSRF-Token": csrf }, data: { status: "active" } },
  );
  expect(response.ok()).toBeTruthy();
}

/** Open one static test site: the sample page embedding the real snippet. */
async function openTestSite(
  page: Page,
  locator: string,
  site: "store-a" | "store-b",
): Promise<void> {
  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=${site}`,
  );
  await expect(page.getByTestId("sample-snippet")).toContainText(locator);
}

test("two static sites, two tenants: each widget answers only from its own knowledge", async ({
  page,
}) => {
  test.setTimeout(180_000);

  // --- tenant A ----------------------------------------------------------
  await registerUser(page, uniqueEmail("widget-a"));
  const a = await createOrgAndBot(page, "Site A bot");
  await activateBot(page, a.tenantId, a.botId);
  await publishKnowledge(page, a.tenantId, a.botId, mdFor("Store A", "7:00"));
  await page.context().clearCookies();

  // --- tenant B ----------------------------------------------------------
  await registerUser(page, uniqueEmail("widget-b"));
  const b = await createOrgAndBot(page, "Site B bot");
  await activateBot(page, b.tenantId, b.botId);
  await publishKnowledge(page, b.tenantId, b.botId, mdFor("Store B", "9:00"));
  await page.context().clearCookies();

  await openTestSite(page, a.locator, "store-a");
  const bubble = page.getByTestId("widget-bubble");
  await expect(bubble).toBeVisible();
  await bubble.click();
  const frame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  await expect(frame).toBeVisible();
  await expect(frame.getByTestId("widget-title")).toContainText(/Site A/i, {
    timeout: 20_000,
  });
  const inputA = frame.getByTestId("widget-input");
  await expect(inputA).toBeVisible();
  await inputA.fill("When do you open?");
  await frame.getByTestId("widget-send").click();
  const replyA = frame.getByTestId("widget-ai-msg").last();
  await expect(
    replyA,
    "tenant A answers with its OWN knowledge (stub model)",
  ).toContainText("7:00", { timeout: 45_000 });
  const answerA = await replyA.textContent();
  expect(answerA ?? "").not.toContain("9:00");

  // --- site B must answer from tenant B's knowledge ----------------------
  await openTestSite(page, b.locator, "store-b");
  const bubbleB = page.getByTestId("widget-bubble");
  await expect(bubbleB).toBeVisible();
  await bubbleB.click();
  const frameB = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  const inputB = frameB.getByTestId("widget-input");
  await expect(inputB).toBeVisible();
  await inputB.fill("When do you open?");
  await frameB.getByTestId("widget-send").click();
  const replyB = frameB.getByTestId("widget-ai-msg").last();
  await expect(replyB).toContainText("9:00", { timeout: 45_000 });
  const answerB = await replyB.textContent();
  expect(answerB ?? "").not.toContain("7:00");
});
