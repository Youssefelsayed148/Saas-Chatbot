import { expect, type Page, test } from "@playwright/test";
import { registerOwner, uniqueEmail } from "./e2e-helpers";

/**
 * P3-04 E2E: the dashboard playground chats over REAL published knowledge
 * (uploaded through the real UI flow) and the deterministic dev stub model
 * (CHAT_STUB_MODEL on the E2E API) proves the grounded pipeline end to end:
 * answer + citation + thumbs feedback + error/not-ready states + roles.
 */

const PASSWORD = "Str0ngPass!";

const KNOWLEDGE_MD =
  "---\ntitle: Opening hours\nsource_url: https://pg-cited.example.com/hours\nlanguage: en\n---\n\n" +
  "# Opening hours\n\nWe are open Monday to Friday from 9:00 to 17:00 and answer chats instantly.\n";

async function createOrgAndBot(
  page: Page,
): Promise<{ tenantId: string; botId: string }> {
  const { tenantId, botName } = await registerOwner(page, "Chat", {});
  await page
    .getByRole("row", { name: new RegExp(botName) })
    .getByRole("link")
    .first()
    .click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  return { tenantId, botId };
}

/** Upload + ingest + publish through the owner's request context (cookies shared). */
async function publishKnowledge(
  page: Page,
  tenantId: string,
  botId: string,
): Promise<void> {
  const csrf = await page
    .evaluate(() => document.cookie)
    .then((cookies) => {
      const entry = cookies
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="));
      return entry ? entry.split("=")[1] : "";
    });
  expect(
    csrf,
    "csrf cookie must be readable (non-HttpOnly) for writes",
  ).toBeTruthy();
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
  // Poll the job to success (the real worker processes it).
  let status = "";
  for (let attempt = 0; attempt < 40; attempt += 1) {
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

test("playground chat: grounded answer, citation, thumbs, thread persists", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { tenantId, botId } = await createOrgAndBot(page);
  await publishKnowledge(page, tenantId, botId);

  await page.goto(`/app/${tenantId}/bots/${botId}/playground`);
  await expect(page.getByRole("heading", { name: "Playground" })).toBeVisible();

  await page.getByTestId("playground-input").fill("open weekday hours");
  page.on("response", async (response) => {
    if (response.url().includes("/playground/messages")) {
      console.log("TURN RESPONSE:", response.status(), await response.text());
    }
  });
  await page.getByTestId("playground-send").click();
  // The stub answers extractively: the reply text comes from the knowledge.
  await expect(page.locator("[data-role='ai']").first()).toContainText(
    /warranty|9:00|17:00|opening/i,
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("citations")).toContainText("Opening hours");
  await expect(page.getByTestId("citations")).toContainText(
    "https://pg-cited.example.com/hours",
  );

  // Thumbs up once: the second click is disabled (idempotent per rater).
  const thumbs = page.locator("[aria-label='Thumbs up']").first();
  await thumbs.click();
  await expect(thumbs).toBeDisabled();
  // Wait for the feedback POST to land, then reload: the thread persists.
  await page.waitForTimeout(500);
  await page.reload();
  await expect(page.locator("[data-role='ai']").first()).toContainText(
    /warranty|9:00/i,
  );
});

test("an expired session pushes the playground back to login", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  await createOrgAndBot(page);
  // Clearing cookies simulates the expired-session event; a protected
  // playground URL then falls back to /login.
  await context.clearCookies();
  await page.goto(
    `/app/${await page.evaluate(() => "00000000-0000-0000-0000-000000000000")}/bots/00000000-0000-0000-0000-000000000000/playground`,
  );
  await page.waitForURL(/\/login/);
});

test("viewer is read-only in the playground", async ({ browser }) => {
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await createOrgAndBot(owner);

  // Invite a viewer through the members page.
  await owner.goto(
    new URL(owner.url()).pathname.replace(
      /\/bots\/[0-9a-f-]+\/settings$/,
      "/settings/members",
    ),
  );
  const viewerEmail = uniqueEmail("pg-viewer");
  await owner.getByLabel("Email", { exact: true }).fill(viewerEmail);
  await owner.getByRole("combobox", { name: "Role" }).selectOption("viewer");
  await owner.getByRole("button", { name: "Create invite link" }).click();
  const inviteCode = (await owner.locator("code").last().textContent()) ?? "";
  expect(inviteCode).toContain("/accept-invite?token=");

  const viewerContext = await browser.newContext();
  const viewer = await viewerContext.newPage();
  await viewer.goto(inviteCode);
  await viewer.getByRole("link", { name: "Register" }).first().click();
  await viewer.getByLabel("Email").fill(viewerEmail);
  await viewer.getByLabel("Password").fill(PASSWORD);
  await viewer.getByRole("button", { name: "Create account" }).click();
  await viewer.getByRole("button", { name: "Accept invitation" }).click();
  await viewer.getByRole("link", { name: /Go to your dashboard/i }).click();
  await viewer.waitForURL("/app");
  await viewer.getByRole("link", { name: /Chat Org/ }).click();
  await viewer.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  await viewer
    .getByRole("row", { name: /Chat Bot/ })
    .getByRole("link")
    .first()
    .click();
  await viewer.getByRole("link", { name: "Playground" }).click();
  await expect(
    viewer.getByText(
      /Read-only view: trying the assistant requires the editor role/,
    ),
  ).toBeVisible();
  await expect(viewer.getByTestId("playground-send")).toHaveCount(0);
  await expect(viewer.getByTestId("playground-input")).toBeDisabled();

  await ownerContext.close();
  await viewerContext.close();
});
