import { expect, type Page, test } from "@playwright/test";

/**
 * P4-05 E2E: per-bot workspace shell (Overview/Playground/etc.) + the Overview
 * analytics page showing MEASURED numbers produced by real visitor flows —
 * including per-bot scoping (tenant A's Overview shows only bot A's numbers).
 */

const PASSWORD = "Str0ngPass!";

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

const md = (name: string, hours: string) =>
  `---\ntitle: ${name} hours\nsource_url: https://${name}.example.com/hours\nlanguage: en\n---\n\n# ${name} opening hours\n\n${name} opens at ${hours}.\n`;

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

async function registerAndPrepare(page: Page, store: string, hours: string) {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail(`ovl-${store}`));
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/app");
  const orgName = `Overview Org ${store} ${Date.now()}`;
  await page.getByLabel("Name").fill(orgName);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  const tenantId = new URL(page.url()).pathname.split("/")[2];
  const botName = `${store} Bot ${Date.now()}`;
  await page.getByLabel("Bot name").fill(botName);
  await page.getByRole("button", { name: "Create bot" }).click();
  await page
    .getByRole("row", { name: new RegExp(botName) })
    .getByRole("link")
    .first()
    .click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  const csrf = await csrfToken(page);
  await page.request.patch(`/api/v1/tenants/${tenantId}/bots/${botId}`, {
    headers: { "X-CSRF-Token": csrf },
    data: { status: "active" },
  });
  const upload = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/sources/files`,
    {
      headers: { "X-CSRF-Token": csrf },
      multipart: {
        files: {
          name: "hours.md",
          mimeType: "text/markdown",
          buffer: Buffer.from(md(store, hours), "utf-8"),
        },
      },
    },
  );
  expect(upload.status()).toBe(201);
  const start = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/ingestion`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: {},
    },
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
  const locator = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json()) as { config: Record<string, string>; widget_locator: string };
  return { tenantId, botId, locator: String(locator.widget_locator), botName };
}

async function visitAndLead(
  page: Page,
  locator: string,
  question: string,
  lead: boolean,
): Promise<void> {
  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=store`,
  );
  const bubble = page.getByTestId("widget-bubble");
  await expect(bubble).toBeVisible();
  await bubble.click();
  const frame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  const input = frame.getByTestId("widget-input");
  await expect(input).toBeVisible();
  await input.fill(question);
  await frame.getByTestId("widget-send").click();
  await expect(frame.getByTestId("widget-ai-msg").last()).toBeVisible({
    timeout: 45_000,
  });
  if (lead) {
    await frame.getByTestId("widget-lead-open").click();
    const form = frame.getByTestId("widget-lead-form");
    await form.getByTestId("widget-lead-name").fill("Omar Requester");
    await form.getByTestId("widget-lead-email").fill("omar@example.com");
    await form.getByTestId("widget-lead-consent").check();
    await form.getByTestId("widget-lead-submit").click();
    await expect(frame.getByTestId("widget-lead-done")).toBeVisible({
      timeout: 15_000,
    });
  }
}

test("workspace shell + measured overview with per-bot scoping and CSV", async ({
  page,
  browser,
}) => {
  test.setTimeout(240_000);
  const a = await registerAndPrepare(page, "Alpha", "8:00");

  // Tenant B registers in its OWN browser context: sharing the context would
  // replace user A's session cookie (the per-bot 404 the first run exposed).
  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  const b = await registerAndPrepare(pageB, "Beta", "11:00");
  // context B stays open until the scoping assertions made below; the owner
  // session in tenant B is required to read bot B's OWN summary.

  // real visitor activity in tenant A only
  await visitAndLead(page, a.locator, "What are your opening hours?", true);
  await visitAndLead(page, a.locator, "Do you ship to Finland?", false);

  // PROBE: server-side view of the SAME ids through the page's own cookie jar.
  await page.goto(`/app/${a.tenantId}/bots/${a.botId}/overview`);
  await expect(page.getByTestId("overview-title")).toContainText("Overview", {
    timeout: 20_000,
  });

  // Workspace nav exists with exactly the tabs that exist today.
  const nav = page.getByTestId("bot-workspace-nav");
  await expect(nav).toBeVisible();
  for (const tab of [
    "overview",
    "conversations",
    "knowledge",
    "playground",
    "settings",
    "install",
  ]) {
    await expect(nav.getByTestId(`nav-${tab}`)).toBeVisible();
  }

  const section = page.getByTestId("overview-summary");
  await expect(section.locator("[data-test='messages']")).toContainText(
    "Messages: 2",
    {
      timeout: 20_000,
    },
  );
  // Both visits share the browser's stored session for this locator, so the
  // measured numbers have ONE conversation/web open (docs/14 §9 measured data).
  await expect(section).toContainText("Conversations: 1");
  await expect(section).toContainText("Widget opens: 1");
  await expect(section).toContainText("Leads: 1");

  // Per-bot/tenant scoping: user A's session must NEVER read bot B's numbers.
  expect(
    (
      await page.request.get(
        `/api/v1/tenants/${b.tenantId}/bots/${b.botId}/analytics/summary`,
      )
    ).status(),
  ).toBe(404);
  // Tenant B's own summary is all zeros (measured, no activity).
  const scoped = await pageB.request.get(
    `/api/v1/tenants/${b.tenantId}/bots/${b.botId}/analytics/summary`,
  );
  expect(scoped.status()).toBe(200);
  const scopedSummary = (await scoped.json()) as {
    messages: number;
    leads: number;
  };
  expect(scopedSummary.messages).toBe(0);
  expect(scopedSummary.leads).toBe(0);

  // CSV export reachable for the owning tenant (documented, real file).
  const csv = await page.request.get(
    `/api/v1/tenants/${a.tenantId}/bots/${a.botId}/analytics/leads.csv`,
  );
  expect(csv.status()).toBe(200);
  expect(csv.headers()["content-type"]).toContain("text/csv");
  await contextB.close();
});

test("unanswered list shows the question the bot could not confirm", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const a = await registerAndPrepare(page, "Gamma", "6:00");
  await visitAndLead(page, a.locator, "Do you sell patio umbrellas?", false);
  await page.goto(`/app/${a.tenantId}/bots/${a.botId}/overview`);
  await page.getByTestId("range-apply").click();
  await expect(
    page.getByTestId("unanswered").locator("li").first(),
  ).toContainText(/patio umbrellas/i, { timeout: 20_000 });
});
