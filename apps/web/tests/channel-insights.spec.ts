import { createHmac } from "node:crypto";

import { expect, request, test, type Page } from "@playwright/test";

import { registerAndPrepareBot } from "./e2e-helpers";

/** P6-05b E2E: mixed-channel inbox, insights by channel, contacts channels.
 *
 * A website conversation is created through the widget public API;
 * a WhatsApp and an Instagram conversation are driven through the real signed
 * events endpoint with a fake Many peer (inbound only, as in P6-05 e2e).
 * All assertions run at 360px and re-checked with the document in RTL. */

const MANY_BASE_URL = "https://many.example.test";
const API_PORT = process.env.E2E_API_PORT ?? "8000";

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

function signedEvent(
  connectionId: string,
  secret: string,
  payload: Record<string, unknown>,
): { headers: Record<string, string>; payload: unknown } {
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac("sha256", secret)
    .update(`${timestamp}.${body}`)
    .digest("hex");
  return {
    headers: {
      "X-Osiris-Connection": connectionId,
      "X-Osiris-Timestamp": String(timestamp),
      "X-Osiris-Signature": `sha256=${signature}`,
    },
    payload: JSON.parse(body),
  };
}

interface ChannelPeer {
  connectionId: string;
  secret: string;
  displayName: string;
  channel: string;
  contactName: string;
}

async function fits360Rtl(page: Page, paths: string[]): Promise<void> {
  for (const path of paths) {
    await page.goto(path);
    await page.locator("html").evaluate((el) => el.setAttribute("dir", "rtl"));
    await page.waitForTimeout(300);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBeTruthy();
  }
  await page.locator("html").evaluate((el) => el.removeAttribute("dir"));
}

test("mixed channel inbox, insights and contacts at 360px with RTL", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 360, height: 800 });
  const { tenantId, botId, locator } = await registerAndPrepareBot(
    page,
    "insights-p6",
  );

  // Staff API path (the registerAndPrepareBot operator is already platform
  // staff). The free placeholder plan allows one connection, so lift the
  // tenant to business for two delegated channels; AI off keeps the e2e
  // deterministically inbound-only (the worker ingests but sends nothing).
  const csrf = await csrfToken(page);
  const headers = { "X-CSRF-Token": csrf };
  const planPatch = await page.request.patch(
    `/api/v1/platform/tenants/${tenantId}/plan`,
    {
      headers,
      data: {
        plan_label: "business",
        reason: "P6-05b E2E coverage needs two channel connections",
      },
    },
  );
  expect(planPatch.ok()).toBeTruthy();
  const createConnection = async (
    channel: string,
    displayName: string,
  ): Promise<{ id: string; secret: string }> => {
    const response = await page.request.post(
      "/api/v1/platform/channel-connections",
      {
        headers,
        data: {
          tenant_id: tenantId,
          bot_id: botId,
          channel,
          display_name: displayName,
          many_base_url: MANY_BASE_URL,
        },
      },
    );
    expect(response.status()).toBe(201);
    const data = (await response.json()) as { id: string; secret: string };
    return { id: data.id, secret: data.secret };
  };
  const wa = await createConnection("whatsapp", "WA Hotline");
  const ig = await createConnection("instagram", "Insta Desk");
  for (const peer of [wa, ig]) {
    const patch = await page.request.patch(
      `/api/v1/platform/channel-connections/${peer.id}`,
      { headers, data: { ai_enabled: false } },
    );
    expect(patch.ok()).toBeTruthy();
  }

  // Website conversation through the real widget pipeline.
  const session = await page.request.post(
    `/api/public/v1/widgets/${locator}/sessions`,
    { data: {} },
  );
  expect(session.status()).toBe(201);
  const sessionData = (await session.json()) as {
    session_id: string;
    token: string;
  };
  const websiteChat = await page.request.post(
    `/api/public/v1/sessions/${sessionData.session_id}/messages`,
    {
      headers: { "X-Session-Token": sessionData.token },
      data: { text: "What are your opening hours?" },
    },
  );
  expect(websiteChat.status()).toBe(201);

  // Fake Many peers post one campaign-origin message per channel.
  const peers: ChannelPeer[] = [
    {
      connectionId: wa.id,
      secret: wa.secret,
      displayName: "WA Hotline",
      channel: "whatsapp",
      contactName: "وسام الويب",
    },
    {
      connectionId: ig.id,
      secret: ig.secret,
      displayName: "Insta Desk",
      channel: "instagram",
      contactName: "Instagram Guest",
    },
  ];
  const api = await request.newContext();
  for (const [index, peer] of peers.entries()) {
    const campaign = index === 0 ? "Spring" : "Autumn";
    const event = signedEvent(peer.connectionId, peer.secret, {
      version: 1,
      event_id: `p6b-${Date.now()}-${index}`,
      event_type: "message.received",
      connection_id: peer.connectionId,
      occurred_at: new Date().toISOString(),
      channel: peer.channel,
      external_contact_id: `p6b-contact-${index}`,
      contact: { name: peer.contactName, handle: `@p6b-${index}` },
      external_conversation_id: `p6b-conversation-${index}`,
      external_message_id: `p6b-message-${Date.now()}-${index}`,
      type: "text",
      text:
        index === 0
          ? "مرحبا، أحتاج مساعدة في طلبي."
          : "Hello, I need help with my order.",
      received_at: new Date().toISOString(),
      origin: { type: "campaign", campaign_name: campaign },
    });
    const posted = await api.post(
      `http://127.0.0.1:${API_PORT}/api/channels/manyosiris/events`,
      {
        headers: event.headers,
        data: event.payload,
      },
    );
    expect(posted.status()).toBe(202);
    expect(await posted.json()).toEqual({ status: "accepted" });
  }

  // Inbox: three rows with channel labels; the WhatsApp row names its
  // connection; the campaign note stays on the thread.
  await page.goto(`/app/${tenantId}/inbox`);
  await expect(page.getByTestId("inbox-list")).toBeVisible();
  await expect(
    page.locator('[data-testid="inbox-list"] .inbox-row'),
  ).toHaveCount(3, { timeout: 60_000 });
  const waRow = page
    .locator(".inbox-row")
    .filter({ hasText: "WhatsApp" })
    .filter({ hasText: "WA Hotline" });
  await expect(waRow).toHaveCount(1);
  await expect(
    page.locator(".inbox-row").filter({ hasText: "Instagram" }),
  ).toHaveCount(1);
  await expect(
    page.locator(".inbox-row").filter({ hasText: "Website" }),
  ).toHaveCount(1);

  // Filter to one channel: the advanced panel starts closed; open it for the
  // select, then narrow the list (360px keeps everything single-column).
  const advanced = page.locator("details.advanced-filters");
  await advanced.evaluate((element) => {
    (element as HTMLDetailsElement).open = true;
  });
  const channelFilter = advanced
    .locator("[data-testid=inbox-channel-filter]")
    .first();
  await expect(channelFilter).toBeVisible({ timeout: 10_000 });
  await channelFilter.selectOption("whatsapp");
  // Close the panel again: it overlays the first row of the list.
  await advanced.evaluate((element) => {
    (element as HTMLDetailsElement).open = false;
  });
  await expect(
    page.locator('[data-testid="inbox-list"] .inbox-row'),
  ).toHaveCount(1);
  await expect(page.getByTestId("inbox-row-connection")).toContainText(
    "WA Hotline",
  );

  // Thread header keeps the campaign line and shows the connection.
  await page.locator('[data-testid="inbox-list"] .inbox-row a').first().click();
  await expect(page.getByTestId("inbox-campaign")).toHaveText(
    "From campaign: Spring",
  );
  await expect(page.getByTestId("inbox-connection")).toContainText(
    "WA Hotline",
  );
  await expect(page.locator('[data-role="visitor"]').first()).toContainText(
    "مرحبا، أحتاج مساعدة في طلبي",
  );

  // Insights: the by-channel breakdown matches the inbox counts (1 WhatsApp
  // conversation in the filtered list; both campaign conversations counted).
  await page.goto(`/app/${tenantId}/analytics`);
  const table = page.getByTestId("insights-channel-table");
  await expect(table).toBeVisible({ timeout: 20_000 });
  const waRowInsights = table.getByRole("row", { name: /WhatsApp/ });
  await expect(waRowInsights).toBeVisible();
  const campaignList = page.getByTestId("insights-campaign-list");
  await expect(campaignList).toContainText("Spring");
  await expect(campaignList).toContainText("Autumn");
  // Insights narrowly agree with the inbox total for the same channel.
  await page.getByTestId("insights-channel-filter").selectOption("whatsapp");
  await expect(
    page.getByRole("heading", { name: "Conversation outcomes" }),
  ).toBeVisible();
  await expect(
    page
      .locator(".insights-kpis")
      .getByText("Conversations", { exact: true })
      .locator("..")
      .getByText("1", { exact: true }),
  ).toBeVisible();

  // Contacts: channel column shows the new Meta channel; filter narrows.
  await page.goto(`/app/${tenantId}/contacts`);
  const contactsFilter = page.getByTestId("contacts-channel-filter");
  await expect(contactsFilter).toBeVisible();
  await contactsFilter.selectOption("whatsapp");
  await expect(
    page.locator("table tbody tr").filter({ hasText: "وسام الويب" }).first(),
  ).toBeVisible();

  // 360px + RTL with no horizontal overflow everywhere the ticket touches.
  await fits360Rtl(page, [
    `/app/${tenantId}/inbox`,
    `/app/${tenantId}/analytics`,
    `/app/${tenantId}/contacts`,
  ]);
  await api.dispose();
});
