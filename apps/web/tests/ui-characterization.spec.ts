import { expect, test, type Page } from "@playwright/test";
import { registerAdmin, registerOperator } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

test.afterEach(async ({ page }) => {
  // Wait for every route handler to settle before the page fixture closes.
  // Errors remain visible; none are ignored or retried.
  await page.unrouteAll({ behavior: "wait" });
});

async function staff(page: Page) {
  const email = `ui-staff.${Date.now()}@example.com`;
  const result = await registerAdmin(page, "UI characterization", { email });
  promoteToStaff(email);
  return result;
}

test("tenant data: operator deletion requires exact name and a meaningful reason", async ({
  page,
}) => {
  const { tenantId } = await registerOperator(page, "Delete validation", {
    organizationName: "Deletion validation",
  });
  let deletes = 0;
  page.on("request", (request) => {
    if (request.method() === "DELETE") deletes++;
  });
  await page.goto(`/app/${tenantId}/settings/data`);
  await expect(
    page.getByRole("button", { name: "Download export" }),
  ).toBeVisible();
  const submit = page.getByRole("button", {
    name: "Schedule organization deletion",
  });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/Type.*to confirm/).fill("wrong name");
  await page.getByLabel("Reason for deletion").fill("Review completed");
  await expect(submit).toBeDisabled();
  await page.getByLabel(/Type.*to confirm/).fill("Deletion validation");
  await page.getByLabel("Reason for deletion").fill("ab");
  await expect(submit).toBeDisabled();
  await page.getByLabel("Reason for deletion").fill("Review completed");
  await expect(submit).toBeEnabled();
  await submit.click();
  const confirmation = page.getByRole("dialog", {
    name: "Delete this organization?",
  });
  await expect(confirmation).toBeVisible();
  await expect(
    confirmation.getByText("bots: 1", { exact: true }),
  ).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "Delete organization now" }),
  ).toBeDisabled();
  await confirmation
    .getByLabel("Confirm organization name")
    .fill("Deletion validation");
  await expect(
    confirmation.getByRole("button", { name: "Delete organization now" }),
  ).toBeEnabled();
  await confirmation
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(confirmation).not.toBeVisible();
  expect(deletes).toBe(0);
});

test("tenant data: admin can review but only staff sees deletion; viewer is denied", async ({
  page,
}) => {
  const { tenantId } = await registerAdmin(page, "Data roles");
  const session = await (await page.request.get("/api/v1/auth/me")).json();
  expect(
    session.memberships.some(
      (m: { tenant_id: string }) => m.tenant_id === tenantId,
    ),
  ).toBe(true);
  for (const role of ["admin", "viewer"]) {
    await page.route("**/api/v1/auth/me", async (route) => {
      const me = session;
      await route.fulfill({
        json: {
          ...me,
          memberships: me.memberships.map((m: { tenant_id: string }) => ({
            ...m,
            role,
          })),
        },
      });
    });
    await page.goto(`/app/${tenantId}/settings/data`);
    if (role === "admin")
      await expect(
        page.getByRole("button", { name: "Download export" }),
      ).toBeVisible();
    else
      await expect(
        page.getByText("Administrator access is required."),
      ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Schedule organization deletion" }),
    ).toHaveCount(0);
    await page.unroute("**/api/v1/auth/me");
  }
});

test("platform operations: reason gates retry and cancel, audit search keeps its query", async ({
  page,
}) => {
  await staff(page);
  const actions: unknown[] = [];
  await page.route("**/api/v1/platform/operations/jobs**", async (route) => {
    if (route.request().method() === "POST") {
      actions.push({
        url: new URL(route.request().url()).pathname,
        body: route.request().postDataJSON(),
      });
      await route.fulfill({ json: { id: "fixture-job", status: "pending" } });
    } else
      await route.fulfill({
        json: {
          counts: { failed: 1, pending: 1 },
          jobs: [
            {
              id: "failed-job",
              type: "ingestion",
              status: "failed",
              attempts: 1,
              error: "Fixture failure",
            },
            {
              id: "pending-job",
              type: "ingestion",
              status: "pending",
              attempts: 0,
              error: null,
            },
          ],
        },
      });
  });
  await page.goto("/platform/operations");
  const failed = page.getByRole("row").filter({ hasText: "Fixture failure" });
  await expect(failed.getByRole("button", { name: "Retry" })).toBeDisabled();
  await page.getByLabel("Reason for job action").fill("Retry after review");
  await failed.getByRole("button", { name: "Retry" }).click();
  await expect.poll(() => actions.length).toBe(1);
  expect(actions[0]).toEqual({
    url: "/api/v1/platform/operations/jobs/failed-job/retry",
    body: { reason: "Retry after review" },
  });
  await page.getByLabel("Reason for job action").fill("Cancel after review");
  await page
    .getByRole("row")
    .filter({ has: page.locator('td[data-status="pending"]') })
    .getByRole("button", { name: "Cancel" })
    .click();
  await expect.poll(() => actions.length).toBe(2);
  expect(actions[1]).toEqual({
    url: "/api/v1/platform/operations/jobs/pending-job/cancel",
    body: { reason: "Cancel after review" },
  });
  await page.getByLabel("Search audit actions").fill("platform");
  const search = page.waitForRequest((request) =>
    request.url().includes("/platform/audit?q=platform"),
  );
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await search;
});

test("platform organization overview exposes only name, plan and status editing", async ({
  page,
}) => {
  const { tenantId } = await staff(page);
  await page.goto(`/platform/clients/${tenantId}`);
  await expect(page.getByRole("tabpanel", { name: "Overview" })).toContainText(
    "Plan",
  );
  await expect(page.getByLabel("Status")).toHaveValue("active");
  await expect(page.getByLabel("Quota overrides (JSON)")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Pause bot" })).toHaveCount(0);
});

test("inbox viewer cannot mutate AI, human or resolved conversations", async ({
  page,
}) => {
  const { tenantId } = await registerAdmin(page, "Inbox viewer");
  const session = await (await page.request.get("/api/v1/auth/me")).json();
  expect(
    session.memberships.some(
      (m: { tenant_id: string }) => m.tenant_id === tenantId,
    ),
  ).toBe(true);
  await page.route("**/api/v1/auth/me", async (route) => {
    const me = session;
    await route.fulfill({
      json: {
        ...me,
        memberships: me.memberships.map((m: object) => ({
          ...m,
          role: "viewer",
        })),
      },
    });
  });
  for (const [mode, status] of [
    ["ai", "open"],
    ["human", "open"],
    ["ai", "resolved"],
  ]) {
    await page.route(
      `**/api/v1/tenants/${tenantId}/conversations/fixture`,
      (route) =>
        route.fulfill({
          json: {
            conversation: {
              id: "fixture",
              bot_id: "fixture",
              contact_id: null,
              channel: "website",
              mode,
              status,
              assigned_user_id: null,
              tags: ["vip"],
            },
            messages: [
              {
                id: "message",
                sender_type: "visitor",
                text: "مرحبا",
                citations: [],
                created_at: "2026-10-15T09:00:00Z",
                needs_human: false,
                can_answer: null,
              },
            ],
          },
        }),
    );
    await page.goto(`/app/${tenantId}/inbox/fixture`);
    await expect(page.getByTestId("inbox-thread")).toContainText("مرحبا");
    for (const name of [
      "Take over",
      "Return to AI",
      "Resolve",
      "Send reply",
      "Add note",
      "Remove vip tag",
    ]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
        0,
      );
    }
    for (const label of ["Assignee", "Reply", "Internal note", "Add tag"])
      await expect(page.getByLabel(label, { exact: true })).toHaveCount(0);
    await expect(
      page.getByText(
        "Viewer access: replies and conversation changes are disabled.",
      ),
    ).toBeVisible();
    await page.unroute(`**/api/v1/tenants/${tenantId}/conversations/fixture`);
  }
});

test("widget 429 displays the server message verbatim", async ({ page }) => {
  const message =
    "Your PLACEHOLDER monthly plan limit is reached. لا يمكن إرسال رسالة الآن.";
  await page.route("**/api/public/v1/widgets/verbatim/config", (route) =>
    route.fulfill({
      json: {
        available: true,
        config: {
          bot_name: "Limit test",
          assistant_name: "Assistant",
          welcome_message: { en: "Welcome", ar: "مرحبا" },
          opening_questions: [],
          colour: "#1f7a5c",
          position: "right",
          default_language: "en",
          dir: "ltr",
        },
      },
    }),
  );
  await page.route("**/api/public/v1/widgets/verbatim/sessions", (route) =>
    route.fulfill({
      json: {
        session_id: "limit-session",
        token: "fixture",
        expires_at: "2099-01-01T00:00:00Z",
      },
    }),
  );
  await page.route(
    "**/api/public/v1/sessions/limit-session/messages**",
    (route) =>
      route.request().method() === "POST"
        ? route.fulfill({
            status: 429,
            json: { error: { code: "QUOTA_EXCEEDED", message } },
          })
        : route.fulfill({ json: [] }),
  );
  await page.goto("/widget/frame?locator=verbatim");
  await page.getByTestId("widget-input").fill("Hello");
  await page.getByTestId("widget-send").click();
  await expect(page.getByTestId("widget-error")).toHaveText(message);
});
