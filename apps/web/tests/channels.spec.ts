import { createHmac } from "node:crypto";

import { expect, request, test, type Page } from "@playwright/test";

import { registerAdmin } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

/** P6-05 E2E with a fake ManyOsirisChat peer.
 *
 * The staff part runs against the real disposable backend (platform staff
 * creates the connection, pauses/resumes/rotates/revokes it). The fake peer
 * signs and POSTs contract events to the real events endpoint, exactly like
 * Many would; the worker processes them into the shared inbox pipeline. */

const MANY_BASE_URL = "https://many.example.test";
const API_PORT = process.env.E2E_API_PORT ?? "8000";

interface Connected {
  tenantId: string;
  email: string;
  secret: string;
  displayName: string;
}

/** The Channels tab of one organization workspace (staff). */
async function orgChannels(page: Page, tenantId: string): Promise<void> {
  await page.goto(`/platform/clients/${tenantId}?tab=Channels`);
  await expect(page.getByTestId("org-channels")).toBeVisible();
}

/** The table row of the first connection (the testid sits inside its cell). */
function firstRow(page: Page) {
  return page
    .getByRole("row")
    .filter({ has: page.getByTestId("channel-row") })
    .first();
}

async function createConnection(
  page: Page,
  prefix: string,
): Promise<Connected> {
  const email = `${prefix}.${Date.now()}@example.com`;
  const { tenantId } = await registerAdmin(page, prefix, { email });
  promoteToStaff(email);
  await orgChannels(page, tenantId);
  const displayName = `${prefix} Support WhatsApp`;
  await page
    .getByRole("combobox", { name: "Assistant", exact: true })
    .selectOption({ index: 1 });
  await page
    .getByRole("combobox", { name: "Channel", exact: true })
    .selectOption("whatsapp");
  await page.getByLabel("Connection name").fill(displayName);
  await page.getByLabel("Many base URL").fill(MANY_BASE_URL);
  await page.getByLabel("Many channel reference").fill(`wa-${Date.now()}-${prefix}`);
  await page.getByRole("button", { name: "Create connection" }).click();
  await expect(page.getByTestId("channel-secret")).toBeVisible();
  const reveal = page.getByTestId("channel-secret-reveal");
  const secretValue = await reveal.locator("code").textContent();
  expect(secretValue).toBeTruthy();
  await expect(page.getByTestId("channel-row").first()).toBeVisible();
  return { tenantId, email, secret: secretValue ?? "", displayName };
}

function signedEvent(
  connectionId: string,
  secret: string,
  payload: Record<string, unknown>,
): { headers: Record<string, string>; body: string } {
  const body = JSON.stringify(payload);
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = createHmac("sha256", secret)
    .update(`${timestamp}.${body}`)
    .digest("hex");
  return {
    headers: {
      "Content-Type": "application/json",
      "X-Osiris-Connection": connectionId,
      "X-Osiris-Timestamp": String(timestamp),
      "X-Osiris-Signature": `sha256=${signature}`,
    },
    body,
  };
}

test("staff manage a connection end to end at 360px with RTL", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 360, height: 800 });
  const { tenantId, secret: initialSecret } = await createConnection(
    page,
    "channels-staff",
  );
  await orgChannels(page, tenantId);
  const row = firstRow(page);
  await expect(row).toContainText("Active");
  await expect(row).toContainText("Unknown");

  // Pause and resume.
  await row.getByRole("button", { name: "Pause" }).click();
  await expect(
    page.locator("main").getByText("Connection paused."),
  ).toBeVisible();
  await expect(row).toContainText("Paused");
  await row.getByRole("button", { name: "Resume" }).click();
  await expect(row).toContainText("Active");

  // The AI toggle flips ai_enabled and survives a reload (controlled input:
  // the state changes when the PATCH lands, so click and wait for the notice).
  await row.getByRole("switch").click();
  await expect(
    page.locator("main").getByText("AI replies paused."),
  ).toBeVisible();
  await page.reload();
  await expect(firstRow(page).getByRole("switch")).not.toBeChecked();
  await firstRow(page).getByRole("switch").click();
  await expect(
    page.locator("main").getByText("AI replies allowed."),
  ).toBeVisible();

  // Rotate the secret: the new value is shown once again.
  await firstRow(page).getByRole("button", { name: "Rotate secret" }).click();
  await page
    .getByRole("dialog", { name: /Rotate the connection secret/ })
    .getByRole("button", { name: "Rotate" })
    .click();
  await expect(page.getByTestId("channel-secret")).toBeVisible();
  const rotated = await page
    .getByTestId("channel-secret-reveal")
    .locator("code")
    .textContent();
  expect(rotated).toBeTruthy();
  await page.getByRole("button", { name: "I saved the secret" }).click();
  await expect(page.getByTestId("channel-secret-reveal")).toHaveCount(0);
  expect(rotated).not.toBe(initialSecret);

  // Revoke through the confirmation dialog; the row stays read-only.
  await firstRow(page).getByRole("button", { name: "Revoke" }).click();
  await page
    .getByRole("dialog", { name: /Revoke this connection/ })
    .getByRole("button", { name: "Revoke" })
    .click();
  await expect(firstRow(page).getByText("Revoked")).toBeVisible();
  await expect(firstRow(page).getByRole("button")).toHaveCount(0);

  // The client overview card is read-only and reflects the outage state.
  await page.goto(`/app/${tenantId}`);
  await expect(page.getByTestId("connected-channels")).toBeVisible();
  await expect(page.getByTestId("connected-channel")).toContainText(
    "channels-staff Support WhatsApp",
  );
  await expect(page.getByTestId("connected-channels")).toContainText("Revoked");

  // The staff overview lists the connection and links to its organization.
  await page.goto("/platform/channels");
  await expect(page.getByTestId("channels-list")).toContainText(
    "channels-staff Support WhatsApp",
  );
  await expect(
    page.getByRole("link", { name: "Open organization" }).first(),
  ).toHaveAttribute("href", new RegExp(`/platform/clients/${tenantId}`));

  // Both staff screens fit 360px with the document in RTL (no clipped rows).
  for (const path of [
    "/platform/channels",
    `/platform/clients/${tenantId}?tab=Channels`,
  ]) {
    await page.goto(path);
    await page.locator("html").evaluate((el) => el.setAttribute("dir", "rtl"));
    await page.waitForTimeout(300);
    expect(
      await page.evaluate(() => {
        const element = document.documentElement;
        return element.scrollWidth <= window.innerWidth + 1;
      }),
    ).toBeTruthy();
  }
});

test("fake Many event drives the shared inbox and the overview card", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { tenantId, secret, displayName } = await createConnection(
    page,
    "channels-many",
  );
  const connectionId = await page.evaluate(() => {
    return new Promise<string>((resolve) => {
      void fetch("/api/v1/platform/channel-connections")
        .then((response) => response.json())
        .then((data: { items: Array<{ id: string }> }) =>
          resolve(data.items[0].id),
        );
    });
  });

  // The fake peer posts one signed message.received from a campaign origin.
  const eventPayload = {
    version: 1,
    event_id: `e2e-${Date.now()}`,
    event_type: "message.received",
    connection_id: connectionId,
    occurred_at: new Date().toISOString(),
    channel: "whatsapp",
    external_contact_id: "e2e-contact-1",
    contact: { name: "وسام الإيت", handle: "@osiris-tester" },
    external_conversation_id: "e2e-conversation-1",
    external_message_id: `e2e-message-${Date.now()}`,
    type: "text",
    text: "مرحبا، أحتاج مساعدة في طلبي.",
    received_at: new Date().toISOString(),
    origin: { type: "campaign", campaign_name: "Spring" },
  };
  const signed = signedEvent(connectionId, secret, eventPayload);
  const api = await request.newContext();
  const posted = await api.post(
    `http://127.0.0.1:${API_PORT}/api/channels/manyosiris/events`,
    { headers: signed.headers, data: JSON.parse(signed.body) },
  );
  expect(posted.status()).toBe(202);
  expect((await posted.json()) as { status: string }).toEqual({
    status: "accepted",
  });
  // The worker ingests the event into the shared inbox pipeline. The row
  // preview may already show the localized handoff reply, so match the
  // contact name carried by the event, not the message text.
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`/app/${tenantId}/inbox`);
  const threadLink = page.getByRole("link", { name: /وسام الإيت/ }).first();
  await expect(threadLink).toBeVisible({ timeout: 30_000 });
  await threadLink.click();
  await expect(page.getByRole("heading", { name: "وسام الإيت" })).toBeVisible();
  await expect(page.getByTestId("inbox-connection")).toContainText(
    "Support WhatsApp",
  );
  await expect(page.getByTestId("inbox-campaign")).toHaveText(
    "From campaign: Spring",
  );
  await expect(page.locator('[data-role="visitor"]').first()).toContainText(
    "مرحبا، أحتاج مساعدة في طلبي",
  );
  // The stub assistant answers through the same pipeline; the reply is queued
  // for delivery to Many (pending until the message.status callback).
  await expect(page.locator('[data-role="ai"]').first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("channel-delivery").first()).toContainText(
    "Pending",
  );

  // The client Overview shows the read-only connected channels card.
  await page.goto(`/app/${tenantId}`);
  await expect(page.getByTestId("connected-channels")).toBeVisible();
  await expect(page.getByTestId("connected-channel")).toContainText(
    displayName,
  );
  await expect(page.getByTestId("connected-channel")).toContainText("WhatsApp");
  // The plan-usage meter counts the connection.
  await expect(
    page.getByRole("meter", { name: "Connected channels" }),
  ).toBeVisible();

  // RTL layout fits 360px on the thread and the overview.
  for (const path of [`/app/${tenantId}/inbox`, `/app/${tenantId}`]) {
    await page.goto(path);
    await page.locator("html").evaluate((el) => el.setAttribute("dir", "rtl"));
    await page.waitForTimeout(300);
    expect(
      await page.evaluate(() => {
        const element = document.documentElement;
        return element.scrollWidth <= window.innerWidth + 1;
      }),
    ).toBeTruthy();
  }
  await api.dispose();
});
