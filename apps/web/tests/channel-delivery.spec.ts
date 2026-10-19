import { expect, test } from "@playwright/test";

test("channel delivery and paused composer fit Arabic RTL at 360px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const tenant = "00000000-0000-0000-0000-000000000001";
  const conversation = "00000000-0000-0000-0000-000000000002";
  let connectionStatus = "paused";
  let channel = "whatsapp";
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let data: unknown = [];
    if (url.pathname.endsWith("/auth/me"))
      data = {
        id: "editor",
        email: "editor@example.test",
        is_platform_staff: false,
        memberships: [
          {
            tenant_id: tenant,
            tenant_name: "Arabic client",
            tenant_slug: "arabic",
            role: "editor",
          },
        ],
      };
    else if (url.pathname.endsWith(`/conversations/${conversation}`))
      data = {
        conversation: {
          id: conversation,
          bot_id: "bot",
          contact_id: null,
          channel,
          connection_status: connectionStatus,
          mode: "human",
          status: "open",
          assigned_user_id: "editor",
          tags: [],
          handoff_reason: null,
          last_message_at: null,
        },
        messages: ["sent", "delivered", "read", "failed"].map(
          (status, index) => ({
            id: String(index),
            sender_type: "ai",
            text: "مرحبا بك، يسعدنا مساعدتك.",
            delivery_status: status,
            error_code: "window_closed",
            citations: [],
            can_answer: true,
            needs_human: false,
            created_at: "2026-10-18T10:00:00Z",
          }),
        ),
      };
    else if (url.pathname.endsWith("/inbox"))
      data = { conversations: [], total: 0, limit: 50, offset: 0 };
    else if (url.pathname.endsWith("/counts"))
      data = {
        waiting_human: 0,
        assigned_to_me: 0,
        unread_messages: 0,
        unread_conversations: 0,
      };
    else if (url.pathname.endsWith("/events"))
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": keep-alive\n\n",
      });
    await route.fulfill({ json: data });
  });
  await page.goto(`/app/${tenant}/inbox/${conversation}`);
  await page.locator("html").evaluate((el) => el.setAttribute("dir", "rtl"));
  await expect(page.getByTestId("channel-delivery")).toHaveCount(4);
  await expect(page.getByTestId("channel-delivery").last()).toContainText(
    "reply window has closed",
  );
  await expect(
    page.getByRole("textbox", { name: "Reply", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "Send reply" })).toBeDisabled();
  await expect(
    page.getByText("This channel connection is paused.", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  connectionStatus = "revoked";
  await page.reload();
  await expect(
    page.getByText("This channel connection was revoked.", { exact: false }),
  ).toBeVisible();
  channel = "website";
  await page.reload();
  await expect(page.getByTestId("channel-delivery")).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "Reply", exact: true }),
  ).toBeEnabled();
});
