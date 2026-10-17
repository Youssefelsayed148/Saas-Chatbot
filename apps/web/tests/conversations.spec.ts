import { expect, test } from "@playwright/test";

import { registerAndPrepareBot, uniqueEmail } from "./e2e-helpers";
import { setPlatformStaff } from "./staff-helpers";

/**
 * P4-04 E2E: visitor chat → consent-based lead → the dashboard conversations
 * view shows the thread with citations and the captured lead; the tenant
 * retention setting is editable in the UI.
 */

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
  // Setup needs operator privileges; replies exercise the actual client admin.
  // Use the public widget frame for visitor turns; the sample helper is staff-only.
  const account = await (await page.request.get("/api/v1/auth/me")).json();
  setPlatformStaff(account.email, false);

  await page.goto(`/widget/frame?locator=${encodeURIComponent(locator)}`);
  const frame = page.getByTestId("widget-frame-body");
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
  await expect(page.getByTestId("inbox-status")).toHaveText(
    "Waiting for human",
  );
  await page.getByRole("button", { name: "Take over", exact: true }).click();
  await expect(page.getByTestId("inbox-status")).toHaveText("Open");
  await expect(page.getByTestId("inbox-mode")).toHaveText("Human mode");
  await page
    .getByRole("textbox", { name: "Reply", exact: true })
    .fill("An agent is here to help you.");
  await page.getByRole("button", { name: "Send reply", exact: true }).click();
  await expect(page.getByTestId("inbox-thread")).toContainText(
    "An agent is here to help you.",
  );
  await page
    .getByRole("textbox", { name: "Internal note", exact: true })
    .fill("Follow up about product availability.");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByTestId("inbox-thread")).toContainText(
    "Follow up about product availability.",
  );

  await page.goto(`/widget/frame?locator=${encodeURIComponent(locator)}`);
  const visitorFrame = page.getByTestId("widget-frame-body");
  await expect(
    visitorFrame
      .getByTestId("widget-ai-msg")
      .filter({ hasText: "An agent is here to help you." }),
  ).toContainText("An agent is here to help you.", { timeout: 20_000 });

  await page.goto(`/app/${tenantId}/inbox/${conversationId}`);
  await page.getByRole("button", { name: "Return to AI", exact: true }).click();
  await expect(page.getByTestId("inbox-mode")).toHaveText("AI mode");
  await page.goto(`/widget/frame?locator=${encodeURIComponent(locator)}`);
  const reopenedFrame = page.getByTestId("widget-frame-body");
  const reopenedReplies = reopenedFrame.getByTestId("widget-ai-msg");
  // count() does not wait: let the restored history (incl. the agent reply) render first.
  await expect(
    reopenedReplies.filter({ hasText: "An agent is here to help you." }),
  ).toBeVisible();
  const replyCountBefore = await reopenedReplies.count();
  await reopenedFrame
    .getByTestId("widget-input")
    .fill("Another question after returning to AI");
  await reopenedFrame.getByTestId("widget-send").click();
  await expect(reopenedReplies).toHaveCount(replyCountBefore + 1, {
    timeout: 45_000,
  });
  await expect(reopenedReplies.last()).toBeVisible();
});
