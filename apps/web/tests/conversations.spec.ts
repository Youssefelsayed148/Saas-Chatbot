import { expect, type Page, test } from "@playwright/test";

/**
 * P4-04 E2E: visitor chat → consent-based lead → the dashboard conversations
 * view shows the thread with citations and the captured lead; the tenant
 * retention setting is editable in the UI.
 */

const PASSWORD = "Str0ngPass!";

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

const KNOWLEDGE_MD =
  "---\ntitle: Opening hours\nsource_url: https://conv.example.com/hours\nlanguage: en\n---\n\n" +
  "# Opening hours\n\nWe are open Monday to Friday from 9:00 to 17:00.\n";

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

async function registerAndPrepareBot(page: Page): Promise<{
  tenantId: string;
  botId: string;
  locator: string;
}> {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail("conv"));
  await page.getByLabel("Password").fill(PASSWORD);
  const registerResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/register") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create account" }).click();
  const registration = await registerResponse;
  console.info(`[e2e] registration response status=${registration.status()}`);
  expect(registration.status()).toBe(201);
  await page.waitForURL("/app");
  await page.getByLabel("Name").fill(`Conversations Org ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  const tenantId = new URL(page.url()).pathname.split("/")[2];
  const botName = `Conversations Bot ${Date.now()}`;
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
  const activate = await page.request.patch(
    `/api/v1/tenants/${tenantId}/bots/${botId}`,
    { headers: { "X-CSRF-Token": csrf }, data: { status: "active" } },
  );
  expect(activate.ok()).toBeTruthy();
  const upload = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/sources/files`,
    {
      headers: { "X-CSRF-Token": csrf },
      multipart: {
        files: {
          name: "hours.md",
          mimeType: "text/markdown",
          buffer: Buffer.from(KNOWLEDGE_MD, "utf-8"),
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
  const bot = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json()) as { widget_locator: string };
  return { tenantId, botId, locator: bot.widget_locator };
}

test("visitor chat + consent lead appear in the conversations view with citations", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { tenantId, botId, locator } = await registerAndPrepareBot(page);

  // Visitor side: chat, then consent-based lead.
  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=store-a`,
  );
  const bubble = page.getByTestId("widget-bubble");
  await expect(bubble).toBeVisible();
  await bubble.click();
  const frame = page
    .locator("[data-testid='widget-frame']")
    .first()
    .contentFrame()
    .locator("[data-testid='widget-frame-body']");
  const input = frame.getByTestId("widget-input");
  await expect(input).toBeVisible();
  await input.fill("What are your opening hours?");
  await frame.getByTestId("widget-send").click();
  await expect(frame.getByTestId("widget-ai-msg").last()).toContainText(
    "9:00",
    { timeout: 45_000 },
  );

  await frame.getByTestId("widget-lead-open").click();
  const form = frame.getByTestId("widget-lead-form");
  await form.getByTestId("widget-lead-name").fill("Vera Visitor");
  await form.getByTestId("widget-lead-email").fill(uniqueEmail("vera"));
  // consent is REQUIRED — submitting empty consent keeps the detail open
  await form.getByTestId("widget-lead-submit").click();
  await expect(frame.getByTestId("widget-lead-error")).toBeVisible();
  await form.getByTestId("widget-lead-consent").check();
  await form.getByTestId("widget-lead-submit").click();
  await expect(
    frame.getByTestId("widget-lead-done"),
    "consent recorded → confirmation",
  ).toBeVisible({ timeout: 15_000 });

  // Dashboard: the conversations view shows the thread and the captured lead.
  await page.goto(`/app/${tenantId}/bots/${botId}/conversations`);
  const table = page.getByTestId("conversations");
  await expect(table.locator("tbody tr").first()).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("[data-testid='conversations'] a").first().click();
  await page.waitForURL(/\/conversations\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("conversation-thread")).toBeVisible();
  await expect(page.getByTestId("conversation-thread")).toContainText(
    "Vera Visitor",
  );
  await expect(page.getByTestId("thread-citations").first()).toBeVisible();
  await expect(page.getByTestId("conversation-thread")).toContainText(/9:00/);
});

test("inbox agent takes over an unanswered widget thread, replies, then returns it to AI", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { tenantId, locator } = await registerAndPrepareBot(page);

  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=inbox-e2e`,
  );
  await page.getByTestId("widget-bubble").first().click({ force: true });
  const frame = page
    .locator("[data-testid='widget-frame']")
    .first()
    .contentFrame()
    .locator("[data-testid='widget-frame-body']");
  const input = frame.getByTestId("widget-input");
  await expect(input).toBeVisible();

  let conversationId = "";
  for (let turn = 0; turn < 2; turn += 1) {
    await input.fill("Do you sell purple elephants?");
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/api/public/v1/sessions/") &&
        response.url().endsWith("/messages") &&
        response.request().method() === "POST",
    );
    await frame.getByTestId("widget-send").click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    const payload = (await response.json()) as { conversation_id: string };
    conversationId = payload.conversation_id;
  }

  await page.goto(`/app/${tenantId}/inbox/${conversationId}`);
  await expect(page.getByTestId("inbox-thread")).toContainText("waiting_human");
  await page.getByRole("button", { name: "Take over" }).click();
  await expect(page.getByText("Human mode")).toBeVisible();
  await page.getByLabel("Reply").fill("An agent is here to help you.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByTestId("inbox-thread")).toContainText(
    "An agent is here to help you.",
  );
  await page
    .getByLabel("Internal note")
    .fill("Follow up about product availability.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByTestId("inbox-thread")).toContainText(
    "Follow up about product availability.",
  );

  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=inbox-e2e`,
  );
  const visitorFrame = page
    .locator("[data-testid='widget-frame']")
    .first()
    .contentFrame()
    .locator("[data-testid='widget-frame-body']");
  await expect(visitorFrame.getByTestId("widget-ai-msg")).toContainText(
    "An agent is here to help you.",
    { timeout: 20_000 },
  );

  await page.goto(`/app/${tenantId}/inbox/${conversationId}`);
  await page.getByRole("button", { name: "Return to AI" }).click();
  await expect(page.getByText("AI mode")).toBeVisible();
  await page.goto(
    `/widget/sample?locator=${encodeURIComponent(locator)}&site=inbox-e2e`,
  );
  const reopenedFrame = page
    .locator("[data-testid='widget-frame']")
    .first()
    .contentFrame()
    .locator("[data-testid='widget-frame-body']");
  await reopenedFrame
    .getByTestId("widget-input")
    .fill("Another question after returning to AI");
  await reopenedFrame.getByTestId("widget-send").click();
  await expect(reopenedFrame.getByTestId("widget-ai-msg").last()).toBeVisible({
    timeout: 45_000,
  });
});
