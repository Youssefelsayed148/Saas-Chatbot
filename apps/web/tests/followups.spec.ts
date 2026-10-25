import { expect, test } from "@playwright/test";

import { registerAndPrepareBot, uniqueEmail } from "./e2e-helpers";

test("editor schedules a website follow-up from a contact profile and views measured analytics", async ({
  page,
}) => {
  const { tenantId, locator } = await registerAndPrepareBot(page, "Follow-up");

  const sessionResponse = await page.request.post(
    `/api/public/v1/widgets/${locator}/sessions`,
    { data: { page_origin: null } },
  );
  expect(sessionResponse.status()).toBe(201);
  const session = (await sessionResponse.json()) as {
    session_id: string;
    token: string;
  };
  const widgetHeaders = { "X-Session-Token": session.token };
  expect(
    (
      await page.request.post(
        `/api/public/v1/sessions/${session.session_id}/messages`,
        {
          headers: widgetHeaders,
          data: { text: "Please have an agent contact me." },
        },
      )
    ).status(),
  ).toBe(201);
  const leadResponse = await page.request.post(
    `/api/public/v1/sessions/${session.session_id}/lead`,
    {
      headers: widgetHeaders,
      data: {
        name: "Follow-up visitor",
        email: uniqueEmail("followup-lead"),
        phone: null,
        consent_accepted: true,
      },
    },
  );
  expect(leadResponse.status()).toBe(201);
  const lead = (await leadResponse.json()) as { contact_id: string };

  await page.goto(`/app/${tenantId}/contacts/${lead.contact_id}`);
  await expect(
    page.getByRole("heading", { name: "Follow-up visitor" }),
  ).toBeVisible();
  await page
    .getByLabel("Conversation", { exact: true })
    .selectOption({ index: 1 });
  const localSendAt = new Date(Date.now() + 60 * 60 * 1000);
  localSendAt.setMinutes(
    localSendAt.getMinutes() - localSendAt.getTimezoneOffset(),
  );
  await page
    .getByLabel("Send after")
    .fill(localSendAt.toISOString().slice(0, 16));
  await page
    .getByLabel("Message", { exact: true })
    .fill("We have reviewed your request.");
  await page.getByRole("button", { name: "Schedule follow-up" }).click();
  await expect(
    page.getByText(/scheduled.*We have reviewed your request/),
  ).toBeVisible();

  await page.goto(`/app/${tenantId}/analytics`);
  await expect(page.getByRole("heading", { name: "Insights" })).toBeVisible();
  await expect(
    page.locator(".ui-card", { hasText: "Conversation outcomes" }),
  ).toContainText(/Conversations\s*1/);
});
