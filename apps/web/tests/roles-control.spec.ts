import { expect, test } from "@playwright/test";
import { registerAdmin, registerOperator, uniqueEmail } from "./e2e-helpers";

test("client admin requests a change and a separate operator triages it", async ({
  page,
  browser,
}) => {
  const { tenantId, botName } = await registerAdmin(page, "Change request");
  const bot = (
    await (await page.request.get(`/api/v1/tenants/${tenantId}/bots`)).json()
  )[0] as { id: string };
  await page.goto(`/app/${tenantId}/bots/${bot.id}/knowledge`);
  await expect(page.getByRole("heading", { name: /knowledge/i })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Upload", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Playground", exact: true }),
  ).toHaveCount(0);
  await page.goto(`/app/${tenantId}/settings/requests`);
  const text = `Please update the opening hours ${Date.now()}`;
  await page.getByLabel("Request type").selectOption("text_change");
  await page.getByLabel("Describe the change").fill(text);
  await page.getByLabel("Attachments").setInputFiles({
    name: "changes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("New opening hours"),
  });
  await page.getByRole("button", { name: "Submit request" }).click();
  await expect(page.getByText(text, { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /changes.txt/ })).toBeVisible();
  const operatorContext = await browser.newContext();
  const operator = await operatorContext.newPage();
  await registerOperator(operator, "Triage operator");
  await operator.goto("/platform/change-requests");
  const request = operator
    .locator("main > ul > li")
    .filter({ has: operator.getByText(text, { exact: true }) });
  await request.getByRole("combobox", { name: /^Status for / }).selectOption("triaged");
  await expect(request.getByText(/Status: triaged/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Status: triaged/)).toBeVisible();
  await operatorContext.close();
  expect(botName).toBeTruthy();
});

test("editor and viewer cannot obtain snippets or enter bot-control surfaces", async ({
  page,
  browser,
}) => {
  const { tenantId } = await registerAdmin(page, "Client roles");
  const bots = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots`)
  ).json()) as { id: string }[];
  const botId = bots[0].id;
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  expect(me.is_platform_staff).toBe(false);
  const adminBot = await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json();
  expect(adminBot.widget_locator).toEqual(expect.any(String));
  expect(adminBot.widget_locator.length).toBeGreaterThan(0);
  await page.goto(`/app/${tenantId}/bots/${botId}/install`);
  await expect(page.getByTestId("install-snippet")).toContainText(
    `data-locator="${adminBot.widget_locator}"`,
  );
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "chatbot_csrf",
  )!.value;
  for (const role of ["editor", "viewer"]) {
    const email = uniqueEmail(role);
    const invited = await page.request.post(
      `/api/v1/tenants/${tenantId}/invitations`,
      { headers: { "X-CSRF-Token": csrf }, data: { email, role } },
    );
    expect(invited.status()).toBe(201);
    const link = (await invited.json()).link_path as string;
    const token = new URL(link, "http://localhost").searchParams.get("token")!;
    const context = await browser.newContext();
    const member = await context.newPage();
    expect(
      (
        await member.request.post("/api/v1/auth/register", {
          data: { email, password: "Str0ngPass!", invite_token: token },
        })
      ).status(),
    ).toBe(201);
    const memberCsrf = (await context.cookies()).find(
      (cookie) => cookie.name === "chatbot_csrf",
    )!.value;
    expect(
      (
        await member.request.post("/api/v1/invitations/accept", {
          headers: { "X-CSRF-Token": memberCsrf },
          data: { token },
        })
      ).status(),
    ).toBe(200);
    await member.goto(`/app/${tenantId}`);
    await expect(
      member.getByRole("heading", { name: "Overview", exact: true }),
    ).toBeVisible();
    await expect(member.getByText("Resource not found.")).toHaveCount(0);
    await member.goto(`/app/${tenantId}/bots/${botId}/overview`);
    for (const name of ["Knowledge", "Playground", "Settings", "Install"])
      await expect(member.getByRole("link", { name, exact: true })).toHaveCount(
        0,
      );
    const bot = await (
      await member.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
    ).json();
    expect(bot.widget_locator).toBeNull();
    expect(bot.config).toEqual({});
    await member.goto(`/app/${tenantId}/bots/${botId}/install`);
    await expect(
      member.getByText("Administrator access required."),
    ).toBeVisible();
    await expect(member.getByTestId("install-snippet")).toHaveCount(0);
    await context.close();
    const members = (await (
      await page.request.get(`/api/v1/tenants/${tenantId}/members`)
    ).json()) as { email: string; user_id: string }[];
    const target = members.find((member) => member.email === email)!;
    expect(
      (
        await page.request.delete(
          `/api/v1/tenants/${tenantId}/members/${target.user_id}`,
          { headers: { "X-CSRF-Token": csrf } },
        )
      ).status(),
    ).toBe(204);
  }
});
