import { expect, type Page, test } from "@playwright/test";
import { registerOwner, uniqueEmail } from "./e2e-helpers";
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

async function openKnowledgeAsOwner(
  page: Page,
  starter = false,
): Promise<void> {
  const email = uniqueEmail("knower");
  const { tenantId, botName } = await registerOwner(page, "K", {
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
  // so the new owner looked like a viewer until a manual reload.
  await openKnowledgeAsOwner(page);
  await expect(page.locator("#knowledge-file-input")).toBeVisible();
  await expect(page.locator("#knowledge-file-input")).toBeEnabled();
});

test("upload, ingest through the worker, preview, publish", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await openKnowledgeAsOwner(page);

  // The Q&A template link is offered to editors.
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
  await openKnowledgeAsOwner(page, true);

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

test("viewer is read-only on knowledge", async ({ browser }) => {
  test.setTimeout(90_000);
  const first = await browser.newContext();
  const owner = await first.newPage();
  await openKnowledgeAsOwner(owner);

  // Invite a viewer through the members page.
  await owner.goto(
    new URL(owner.url()).pathname.replace(
      /\/bots\/[0-9a-f-]+\/knowledge$/,
      "/settings/members",
    ),
  );
  const viewerEmail = uniqueEmail("viewer");
  await owner.getByLabel("Email", { exact: true }).fill(viewerEmail);
  await owner.getByRole("combobox", { name: "Role" }).selectOption("viewer");
  await owner.getByRole("button", { name: "Create invite link" }).click();
  const inviteCode = (await owner.locator("code").last().textContent()) ?? "";
  expect(inviteCode).toContain("/accept-invite?token=");

  const second = await browser.newContext();
  const viewer = await second.newPage();
  await viewer.goto(inviteCode);
  await viewer.getByRole("link", { name: "Register" }).first().click();
  await viewer.getByLabel("Email").fill(viewerEmail);
  await viewer.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await viewer.getByRole("button", { name: "Create account" }).click();
  await viewer.getByRole("button", { name: "Accept invitation" }).click();
  await viewer.getByRole("link", { name: /Go to your dashboard/i }).click();
  await viewer.waitForURL("/app");

  // The viewer opens the bot workspace and its knowledge page.
  await viewer.getByRole("link", { name: /K Org/ }).click();
  await viewer.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  await viewer
    .getByRole("row", { name: /Knowledge Bot/ })
    .getByRole("link")
    .first()
    .click();
  await viewer.waitForURL(/\/settings$/);
  await viewer.getByRole("link", { name: "Knowledge" }).click();
  await viewer.waitForURL(/\/knowledge$/);
  await expect(
    viewer.getByRole("heading", { name: "Knowledge" }),
  ).toBeVisible();
  await expect(
    viewer.getByText(
      /Read-only view: uploads and ingest require the editor role/,
    ),
  ).toBeVisible();
  await expect(
    viewer.getByRole("link", { name: /download the template/ }),
  ).toHaveCount(0);
  const input = viewer.locator("#knowledge-file-input");
  await expect(input).toBeDisabled();
  const main = viewer.locator("main");
  await expect(
    main.getByRole("button", {
      name: /Ingest files|Upload|Publish|Retry|Cancel/,
    }),
  ).toHaveCount(0);

  await first.close();
  await second.close();
});
