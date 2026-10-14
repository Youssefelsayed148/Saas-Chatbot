import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Str0ngPass!";
const uniqueEmail = () =>
  `followup.${Date.now()}.${Math.floor(Math.random() * 1_000_000)}@example.com`;

async function csrf(page: Page): Promise<string> {
  const cookie = await page.evaluate(() => document.cookie);
  return (
    cookie
      .split("; ")
      .find((item) => item.startsWith("chatbot_csrf="))
      ?.split("=")[1] ?? ""
  );
}

test("editor schedules a website follow-up from a contact profile and views measured analytics", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/app");
  await expect(
    page.getByRole("heading", { name: "Your organizations" }),
  ).toBeVisible();
  await page.getByLabel("Name").fill(`Follow-up Org ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);
  const tenantId = new URL(page.url()).pathname.split("/")[2];
  const headers = { "X-CSRF-Token": await csrf(page) };
  const botResponse = await page.request.post(
    `/api/v1/tenants/${tenantId}/bots`,
    {
      headers,
      data: { name: "Follow-up bot" },
    },
  );
  expect(botResponse.status()).toBe(201);
  const bot = (await botResponse.json()) as {
    id: string;
    widget_locator: string;
  };
  const activation = await page.request.patch(
    `/api/v1/tenants/${tenantId}/bots/${bot.id}`,
    {
      headers,
      data: { status: "active" },
    },
  );
  expect(activation.status()).toBe(200);

  const sessionResponse = await page.request.post(
    `/api/public/v1/widgets/${bot.widget_locator}/sessions`,
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
        email: uniqueEmail(),
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
  await page.getByLabel("Conversation").selectOption({ index: 1 });
  const localSendAt = new Date(Date.now() + 60 * 60 * 1000);
  localSendAt.setMinutes(
    localSendAt.getMinutes() - localSendAt.getTimezoneOffset(),
  );
  await page
    .getByLabel("Send after")
    .fill(localSendAt.toISOString().slice(0, 16));
  await page.getByLabel("Message").fill("We have reviewed your request.");
  await page.getByRole("button", { name: "Schedule follow-up" }).click();
  await expect(
    page.getByText(/scheduled.*We have reviewed your request/),
  ).toBeVisible();

  await page.goto(`/app/${tenantId}/analytics`);
  await expect(
    page.getByRole("heading", { name: "Handoff analytics" }),
  ).toBeVisible();
  await expect(page.getByText("Total: 1")).toBeVisible();
});
