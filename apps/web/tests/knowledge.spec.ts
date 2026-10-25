import { expect, type Page, test } from "@playwright/test";
import { registerOperator, uniqueEmail } from "./e2e-helpers";
import { assignStarterPlan } from "./staff-helpers";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * P2 E2E: upload a real Markdown fixture, run the ingest job through the real
 * DB worker (started by the Playwright global setup), preview documents and
 * chunks, publish, and check the role restrictions.
 */

const PASSWORD = "Str0ngPass!";
const FIXTURE = path.join(__dirname, "fixtures", "knowledge-sample.md");

async function openKnowledgeAsOperator(
  page: Page,
  starter = false,
): Promise<void> {
  const email = uniqueEmail("knower");
  const { tenantId, botName } = await registerOperator(page, "K", {
    email,
    botName: `Knowledge Bot ${Date.now()}`,
  });
  if (starter) await assignStarterPlan(page, tenantId, email);
  await page
    .getByRole("row", { name: new RegExp(botName) })
    .getByRole("link")
    .first()
    .click();
  await page.waitForURL(/\/settings$/);
  await page.getByRole("link", { name: "Knowledge" }).click();
  await page.waitForURL(/\/knowledge$/);
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible();
}

test("fresh signup shows the knowledge upload controls without a reload", async ({
  page,
}) => {
  // Regression: the session was not refreshed after self-service provisioning,
  // so the new admin looked like a viewer until a manual reload.
  await openKnowledgeAsOperator(page);
  await expect(page.locator("#knowledge-file-input")).toBeVisible();
  await expect(page.locator("#knowledge-file-input")).toBeEnabled();
});

test("upload, ingest through the worker, preview, publish", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await openKnowledgeAsOperator(page);

  // The Q&A template link is offered to operators.
  await expect(
    page.getByRole("link", { name: /download the template/ }),
  ).toBeVisible();
  const template = await page.request.get(
    (await page
      .getByRole("link", { name: /download the template/ })
      .getAttribute("href")) ?? "",
  );
  expect(template.ok()).toBeTruthy();
  expect(await template.text()).toContain("question,answer,topic,priority");

  // Upload a real Markdown fixture (multipart through the same-origin proxy).
  await page.locator("#knowledge-file-input").setInputFiles({
    name: "sample-brochure.md",
    mimeType: "text/markdown",
    buffer: readFileSync(FIXTURE),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  const sources = page.locator("[data-testid='sources-list']");
  await expect(sources).toContainText("sample-brochure.md");
  await expect(sources.locator("[data-source-status]")).toHaveAttribute(
    "data-source-status",
    "stored",
  );

  // Run the ingest; the REAL worker processes the job.
  await page.getByRole("button", { name: "Ingest files" }).click();
  const jobs = page.locator("[data-testid='jobs-list']");
  await expect(jobs.locator("[data-job-status]").first()).toHaveAttribute(
    "data-job-status",
    "succeeded",
    { timeout: 45_000 },
  );

  // Draft documents appear with the chunk preview and the source_url citation.
  await page.getByLabel("View").selectOption("draft");
  const documents = page.locator("[data-testid='documents-list']");
  await expect(documents).toContainText("Opening hours");
  await expect(documents).toContainText("https://sample.example.com/hours");
  await page
    .getByRole("button", { name: /Opening hours/ })
    .first()
    .click();
  await expect(page.locator("[data-testid='chunk-list']")).toContainText("#0");

  // Publishing switches the pointer; the revisions list shows the published row.
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(
    page.getByText(/Published — visitors now use this knowledge/),
  ).toBeVisible();
  await expect(
    page.locator(
      "[data-testid='revisions-list'] [data-revision-status='published']",
    ),
  ).toBeVisible();

  // The published view (default) now shows the documents too.
  await page.getByLabel("View").selectOption("published");
  await expect(documents).toContainText("Opening hours");
});

test("oversize uploads are rejected through the same-origin proxy with 413", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await openKnowledgeAsOperator(page, true);

  // 10 MB + 1 byte: the API's streaming cap rejects it (the proxy forwards it).
  await page.locator("#knowledge-file-input").setInputFiles({
    name: "big.md",
    mimeType: "text/markdown",
    buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 0x61),
  });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText(/Files may be at most 10 MB/)).toBeVisible({
    timeout: 30_000,
  });
  // Nothing was stored by the rejected batch.
  await expect(page.locator("[data-testid='sources-list'] li")).toHaveCount(0);
});

test("viewer cannot access knowledge", async ({ browser }) => {
  test.setTimeout(90_000);
  const first = await browser.newContext();
  const admin = await first.newPage();
  await openKnowledgeAsOperator(admin);

  // Invite a viewer through the members page.
  await admin.goto(
    new URL(admin.url()).pathname.replace(
      /\/bots\/[0-9a-f-]+\/knowledge$/,
      "/settings/members",
    ),
  );
  const viewerEmail = uniqueEmail("viewer");
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

  const second = await browser.newContext();
  const viewer = await second.newPage();
  await viewer.goto(inviteCode);
  // S2: the account exists, so the link flow is sign in, then accept.
  await viewer.getByRole("link", { name: "Sign in" }).click();
  await viewer.getByLabel("Email").fill(viewerEmail);
  await viewer.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await viewer.getByRole("button", { name: "Sign in", exact: true }).click();
  await viewer.getByRole("button", { name: "Accept invitation" }).click();
  await viewer.getByRole("link", { name: /Go to your dashboard/i }).click();
  await viewer.waitForURL("/app");

  // The viewer opens the bot workspace and its knowledge page.
  await viewer.getByRole("link", { name: /K Org/ }).click();
  await viewer.waitForURL(/\/app\/[0-9a-f-]{36}$/);
  const tenantId = new URL(viewer.url()).pathname.split("/")[2];
  const bots = await (
    await viewer.request.get(`/api/v1/tenants/${tenantId}/bots`)
  ).json();
  const botId = bots[0].id;
  await viewer.goto(`/app/${tenantId}/bots/${botId}/knowledge`);
  await expect(viewer).toHaveURL(`/app/${tenantId}`);
  await expect(viewer.locator("#knowledge-file-input")).toHaveCount(0);
  expect(
    (
      await viewer.request.get(
        `/api/v1/tenants/${tenantId}/bots/${botId}/sources`,
      )
    ).status(),
  ).toBe(403);

  await first.close();
  await second.close();
});

test("duplicate upload is skipped; always-include, replace and remove work with confirmations", async ({
  page,
}) => {
  test.setTimeout(150_000);
  await openKnowledgeAsOperator(page);
  const sources = page.locator("[data-testid='sources-list']");
  const fixture = {
    name: "sample-brochure.md",
    mimeType: "text/markdown",
    buffer: readFileSync(FIXTURE),
  };

  await page.locator("#knowledge-file-input").setInputFiles(fixture);
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(sources.locator("li")).toHaveCount(1);

  // The same bytes again: reported as skipped, no second row.
  await page
    .locator("#knowledge-file-input")
    .setInputFiles({ ...fixture, name: "copy-of-brochure.md" });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText(/already uploaded/)).toBeVisible();
  await expect(sources.locator("li")).toHaveCount(1);

  // Always include asks for confirmation.
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByTestId("source-always-include").check();
  await expect(page.getByTestId("source-always-include")).toBeChecked();

  // Replace with a changed version; the source row is kept.
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByTestId("source-replace-input").setInputFiles({
    ...fixture,
    buffer: Buffer.concat([fixture.buffer, Buffer.from("\n\nExtra line.\n")]),
  });
  await expect(page.getByText(/New version stored/)).toBeVisible();
  await expect(sources.locator("li")).toHaveCount(1);

  // Remove goes through a confirm dialog.
  await page.getByTestId("source-delete").click();
  await page.getByRole("button", { name: "Remove file" }).click();
  await expect(page.getByText(/Removed .* from the draft/)).toBeVisible();
  await expect(sources.locator("li")).toHaveCount(0);
});
