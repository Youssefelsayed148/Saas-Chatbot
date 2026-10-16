import { promoteToStaff } from "./staff-helpers";
import { expect, type Page } from "@playwright/test";

const PASSWORD = "Str0ngPass!";
const KNOWLEDGE_MD =
  "---\ntitle: Opening hours\nsource_url: https://conv.example.com/hours\nlanguage: en\n---\n\n" +
  "# Opening hours\n\nWe are open Monday to Friday from 9:00 to 17:00.\n";

export function uniqueEmail(prefix: string): string {
  const local = prefix.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return `${local}.${Date.now()}.${Math.floor(Math.random() * 10_000)}@example.com`;
}

export async function registerAdmin(
  page: Page,
  prefix: string,
  opts: { email?: string; organizationName?: string; botName?: string } = {},
): Promise<{ tenantId: string; botName: string }> {
  const botName = opts.botName ?? `${prefix} Bot ${Date.now()}`;
  await page.goto("/register");
  await page
    .getByLabel("Organization name")
    .fill(opts.organizationName ?? `${prefix} Org ${Date.now()}`);
  await page.getByLabel("First bot name").fill(botName);
  await page.getByLabel("Email").fill(opts.email ?? uniqueEmail(prefix));
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  const registration = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/register") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create account" }).click();
  expect((await registration).status()).toBe(201);
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  return { tenantId: new URL(page.url()).pathname.split("/")[2], botName };
}

export async function registerOperator(
  page: Page,
  prefix: string,
  opts: { email?: string; organizationName?: string; botName?: string } = {},
) {
  const email = opts.email ?? uniqueEmail(prefix);
  const result = await registerAdmin(page, prefix, { ...opts, email });
  promoteToStaff(email);
  await page.reload();
  return result;
}

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

export async function registerAndPrepareBot(
  page: Page,
  prefix = "E2E",
): Promise<{ tenantId: string; botId: string; locator: string }> {
  const operatorEmail = uniqueEmail(prefix);
  const { tenantId, botName } = await registerAdmin(page, prefix, {
    email: operatorEmail,
  });
  promoteToStaff(operatorEmail);
  await page.reload();
  await page
    .getByRole("row", { name: new RegExp(botName) })
    .getByRole("link")
    .first()
    .click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  const headers = { "X-CSRF-Token": await csrfToken(page) };
  const activate = await page.request.patch(
    `/api/v1/tenants/${tenantId}/bots/${botId}`,
    { headers, data: { status: "active" } },
  );
  expect(activate.ok()).toBeTruthy();
  const upload = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/sources/files`,
    {
      headers,
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
  const ingestion = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/ingestion`,
    { headers, data: {} },
  );
  expect([201, 202]).toContain(ingestion.status());

  let jobStatus = "";
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const jobs = await page.request.get(
      `/api/v1/tenants/${tenantId}/bots/${botId}/jobs`,
    );
    const list = (await jobs.json()) as { status: string }[];
    jobStatus = list[0]?.status ?? "missing";
    if (jobStatus === "succeeded" || jobStatus === "failed") break;
    await page.waitForTimeout(500);
  }
  expect(jobStatus, "ingest job must succeed").toBe("succeeded");
  const revisionsResponse = await page.request.get(
    `/api/v1/tenants/${tenantId}/bots/${botId}/revisions`,
  );
  const revisions = (await revisionsResponse.json()) as {
    revisions: { id: string; status: string }[];
  };
  const draft = revisions.revisions.find((row) => row.status === "draft");
  expect(draft, "ingestion must create a draft revision").toBeDefined();
  const publish = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots/${botId}/revisions/${draft?.id}/publish`,
    { headers },
  );
  expect(publish.status()).toBe(200);
  const botResponse = await page.request.get(
    `/api/v1/tenants/${tenantId}/bots/${botId}`,
  );
  const bot = (await botResponse.json()) as { widget_locator: string };
  return { tenantId, botId, locator: bot.widget_locator };
}
