import { expect, type Page, test } from "@playwright/test";
import { registerOperator, uniqueEmail } from "./e2e-helpers";

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
  const { tenantId, botName } = await registerOperator(page, "Chat", {});
  await page
    .getByRole("link", { name: new RegExp(`Open ${botName}`) })
    .click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  return { tenantId, botId };
}

/** Upload + ingest + publish through the admin's request context (cookies shared). */
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
  await expect(page.getByTestId("answer-traces")).toContainText("passed");
  await page.getByTestId("answer-traces").locator("summary").first().click();
  await expect(page.getByTestId("answer-traces")).toContainText(
    "Opening hours",
  );
  await expect(page.getByTestId("answer-traces")).toContainText("cosine");

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

test("playground streams the turn, New session starts an empty thread", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const { tenantId, botId } = await createOrgAndBot(page);
  await page.goto(`/app/${tenantId}/bots/${botId}/playground`);
  await expect(page.getByRole("heading", { name: "Playground" })).toBeVisible();
  await expect(page.getByText("No messages yet")).toBeVisible();

  // The Stop button only exists while a turn is in flight.
  await expect(page.getByTestId("playground-stop")).toHaveCount(0);
  await page
    .getByTestId("playground-input")
    .fill("What are your opening hours?");
  const streamed = page.waitForResponse(
    (response) =>
      response.url().includes("/playground/messages/stream") &&
      response.request().method() === "POST",
  );
  await page.getByTestId("playground-send").click();
  expect((await streamed).status()).toBe(200);

  // No knowledge is published: the canned refusal is the reply, with no sources.
  await expect(page.locator("[data-role='ai']")).toHaveCount(1, {
    timeout: 30_000,
  });
  await expect(page.locator("[data-role='visitor']")).toHaveCount(1);
  await expect(page.getByTestId("citations")).toHaveCount(0);
  await expect(page.getByTestId("playground-stop")).toHaveCount(0);

  await page.getByTestId("playground-new-session").click();
  await expect(page.getByText("No messages yet")).toBeVisible();
  await expect(page.locator("[data-role='ai']")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("No messages yet")).toBeVisible();
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
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await createOrgAndBot(admin);

  // Invite a viewer through the members page.
  await admin.goto(
    new URL(admin.url()).pathname.replace(
      /\/bots\/[0-9a-f-]+\/settings$/,
      "/settings/members",
    ),
  );
  const viewerEmail = uniqueEmail("pg-viewer");
  // S2: invitations target existing users; create the viewer account first in
  // an isolated context so the admin session (shared jar) is not replaced.
  const regContext = await browser.newContext();
  expect(
    (
      await regContext.request.post("/api/v1/auth/register", {
        data: { email: viewerEmail, password: PASSWORD },
      })
    ).status(),
  ).toBe(201);
  await regContext.close();
  await admin.getByLabel("Email", { exact: true }).fill(viewerEmail);
  await admin.getByRole("combobox", { name: "Role" }).selectOption("viewer");
  await admin.getByRole("button", { name: "Create invite link" }).click();
  const inviteCode = (await admin.locator("code").last().textContent()) ?? "";
  expect(inviteCode).toContain("/accept-invite?token=");

  const viewerContext = await browser.newContext();
  const viewer = await viewerContext.newPage();
  await viewer.goto(inviteCode);
  // S2: the account exists, so the link flow is sign in, then accept.
  await viewer.getByRole("link", { name: "Sign in" }).click();
  await viewer.getByLabel("Email").fill(viewerEmail);
  await viewer.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await viewer.getByRole("button", { name: "Sign in", exact: true }).click();
  await viewer.getByRole("button", { name: "Accept invitation" }).click();
  await viewer.getByRole("link", { name: /Go to your dashboard/i }).click();
  await viewer.waitForURL("/app");
  await viewer.getByRole("link", { name: /Chat Org/ }).click();
  await viewer.waitForURL(/\/app\/[0-9a-f-]{36}$/);
  const tenantId = new URL(viewer.url()).pathname.split("/")[2];
  const bots = await (
    await viewer.request.get(`/api/v1/tenants/${tenantId}/bots`)
  ).json();
  const botId = bots[0].id;
  await viewer.goto(`/app/${tenantId}/bots/${botId}/playground`);
  await expect(viewer).toHaveURL(`/app/${tenantId}`);
  await expect(viewer.getByTestId("playground-input")).toHaveCount(0);
  expect(
    (
      await viewer.request.get(
        `/api/v1/tenants/${tenantId}/bots/${botId}/playground/conversation`,
      )
    ).status(),
  ).toBe(403);

  await adminContext.close();
  await viewerContext.close();
});
