import { expect, type Page, test } from "@playwright/test";
import { registerOperator, uniqueEmail } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

/**
 * A2 domain enforcement (#34, #32, #33, #10, #11): the bot's allowed-domains
 * list works at BOTH layers of the widget embed:
 *  - the API session check (the loader forwards the embedding page's
 *    location.hostname → the frame reports it as page_origin);
 *  - the browser CSP: the frame page carries a per-bot frame-ancestors
 *    (computed by the web proxy from the bot config), so unlisted sites
 *    cannot frame the widget at all.
 * The two "sites" are the sample-page helper (/widget/sample, staff-only) on
 * the two loopback hostnames the test deployment serves: 127.0.0.1 (not
 * allowed) and localhost (allowed, with the port wildcard outside
 * production).
 */

const PORT = process.env.E2E_WEB_PORT ?? "3100";
const DENIED_HOST = "127.0.0.1";
const ALLOWED_HOST = "localhost";
const PASSWORD = "Str0ngPass!";

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

async function createOrgAndBot(
  page: Page,
  botName: string,
): Promise<{ tenantId: string; botId: string; locator: string }> {
  const { tenantId } = await registerOperator(page, "WidgetDomain", {
    botName,
  });
  await page.getByRole("link", { name: new RegExp(`Open ${botName}`) }).click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  const bot = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json()) as { widget_locator: string };
  expect(bot.widget_locator).toBeTruthy();
  return { tenantId, botId, locator: bot.widget_locator };
}

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

async function patchAllowedDomains(
  page: Page,
  tenantId: string,
  botId: string,
  domains: string[],
): Promise<void> {
  const csrf = await csrfToken(page);
  const response = await page.request.patch(
    `/api/v1/tenants/${tenantId}/bots/${botId}`,
    {
      headers: { "X-CSRF-Token": csrf },
      data: { config: { allowed_domains: domains } },
    },
  );
  expect(response.ok()).toBeTruthy();
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

/** A registered+promoted staff session for the sample page on `host`. */
async function seedStaffOnHost(page: Page, host: string): Promise<void> {
  const email = uniqueEmail("widget-host");
  const response = await page.request.post(
    `http://${host}:${PORT}/api/v1/auth/register`,
    {
      data: { email, password: PASSWORD },
    },
  );
  expect(response.status()).toBe(201);
  promoteToStaff(email);
}

async function openSampleSite(
  page: Page,
  host: string,
  locator: string,
): Promise<void> {
  await page.goto(
    `http://${host}:${PORT}/widget/sample?locator=${encodeURIComponent(locator)}`,
  );
  await expect(page.getByTestId("sample-snippet")).toContainText(locator);
}

test("an allowed-domains bot answers on the listed host and cannot appear on another", async ({
  page,
}) => {
  test.setTimeout(300_000);

  const locked = await createOrgAndBot(page, "Locked bot");
  await activateBot(page, locked.tenantId, locked.botId);
  await publishKnowledge(
    page,
    locked.tenantId,
    locked.botId,
    mdFor("Locked Store", "7:00"),
  );
  await patchAllowedDomains(page, locked.tenantId, locked.botId, [
    ALLOWED_HOST,
  ]);
  await seedStaffOnHost(page, ALLOWED_HOST);

  // A2.2: the frame page response now carries the per-bot CSP — both scheme
  // forms and the localhost port wildcard (outside production) — and never
  // the unlisted host.
  const frameResponse = await page.request.get(
    `/widget/frame?locator=${encodeURIComponent(locked.locator)}`,
  );
  expect(frameResponse.ok()).toBeTruthy();
  const csp = frameResponse.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("frame-ancestors http://localhost:*");
  expect(csp).toContain("https://localhost:*");
  expect(csp).not.toContain("127.0.0.1");

  // Allowed host embeds the real loader snippet: launcher + grounded answer.
  await openSampleSite(page, ALLOWED_HOST, locked.locator);
  const bubble = page.getByTestId("widget-bubble");
  await expect(bubble).toBeVisible();
  await bubble.click();
  const frame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  await expect(frame).toBeVisible();
  const input = frame.getByTestId("widget-input");
  await expect(input).toBeVisible();
  await input.fill("When do you open?");
  await frame.getByTestId("widget-send").click();
  await expect(frame.getByTestId("widget-ai-msg").last()).toContainText(
    "7:00",
    { timeout: 45_000 },
  );

  // Unlisted host: the browser must refuse to frame (the CSP above), so the
  // chat UI never appears inside the frame.
  await openSampleSite(page, DENIED_HOST, locked.locator);
  await page.getByTestId("widget-bubble").click();
  const deniedFrameBody = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  // A frame load of a fresh locator needs no stored session here: give the
  // (blocked) frame load a grace period before asserting it never rendered.
  await page.waitForTimeout(2500);
  await expect(deniedFrameBody).toHaveCount(0);

  // The same deny is a safe server-side message for non-browser clients —
  // defence signal, not authentication; the CSP is the browser guard.
  const direct = await page.request.post(
    `/api/public/v1/widgets/${encodeURIComponent(locked.locator)}/sessions`,
    { data: { page_origin: `http://${DENIED_HOST}:${PORT}/` } },
  );
  expect(direct.status()).toBe(403);
  const denial = (await direct.json()) as {
    error: { code: string; message: string };
  };
  expect(denial.error.code).toBe("DOMAIN_NOT_ALLOWED");
  expect(denial.error.message).toContain("not allowed");
});

test("an empty allowed-domains list keeps the check off for every site", async ({
  page,
}) => {
  test.setTimeout(300_000);

  const open = await createOrgAndBot(page, "Open bot");
  await activateBot(page, open.tenantId, open.botId);
  await publishKnowledge(
    page,
    open.tenantId,
    open.botId,
    mdFor("Open Store", "9:00"),
  );
  // Unconfigured: the static permissive rule stays (and unlisted page origins
  // are never denied at session creation).

  const frameResponse = await page.request.get(
    `/widget/frame?locator=${encodeURIComponent(open.locator)}`,
  );
  expect(frameResponse.ok()).toBeTruthy();
  const csp = frameResponse.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("frame-ancestors http: https:");

  await openSampleSite(page, DENIED_HOST, open.locator);
  const bubble = page.getByTestId("widget-bubble");
  await expect(bubble).toBeVisible();
  await bubble.click();
  const frame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  const input = frame.getByTestId("widget-input");
  await expect(input).toBeVisible();
  await input.fill("When do you open?");
  await frame.getByTestId("widget-send").click();
  await expect(frame.getByTestId("widget-ai-msg").last()).toContainText(
    "9:00",
    { timeout: 45_000 },
  );

  // The sample page is staff-only and cookies are per host: sign in on this host too.
  await seedStaffOnHost(page, ALLOWED_HOST);
  await openSampleSite(page, ALLOWED_HOST, open.locator);
  await page.getByTestId("widget-bubble").click();
  const secondFrame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  await expect(secondFrame.getByTestId("widget-title")).toContainText(
    /Open bot/i,
    { timeout: 20_000 },
  );
  await expect(secondFrame.getByTestId("widget-input")).toBeVisible();
});
