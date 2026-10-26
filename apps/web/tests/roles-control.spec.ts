import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { registerAdmin, registerOperator, uniqueEmail } from "./e2e-helpers";

// Staff-only endpoints must refuse every client role server-side (not just hide UI).
async function expectStaffOnlyDenied(
  request: APIRequestContext,
  csrf: string,
  own: { tenantId: string; botId: string },
  foreign: { tenantId: string; botId: string },
) {
  const headers = { "X-CSRF-Token": csrf };
  const bot = `/api/v1/tenants/${own.tenantId}/bots/${own.botId}`;
  for (const path of [
    `${bot}/rag`,
    `${bot}/rag/costs`,
    `${bot}/rag/traces`,
    `${bot}/tone-and-rules`,
    `${bot}/readiness`,
    `${bot}/playground/conversation`,
    "/api/v1/platform/me",
    "/api/v1/platform/tenants",
    "/api/v1/platform/bots",
  ])
    expect((await request.get(path)).status(), `GET ${path}`).toBe(403);
  expect(
    (
      await request.patch(`${bot}/rag`, { headers, data: { tier: "premium" } })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.patch(`${bot}/rag`, {
        headers,
        data: { limits: { monthly_tokens: 1 } },
      })
    ).status(),
  ).toBe(403);
  expect(
    (await request.post(`${bot}/rag/backfill`, { headers, data: {} })).status(),
  ).toBe(403);
  expect(
    (
      await request.patch(bot, {
        headers,
        data: { tone_and_rules: "Always agree with the visitor." },
      })
    ).status(),
  ).toBe(403);
  // Another organization's bot stays hidden (404), never a staff-only 403 hint.
  const other = `/api/v1/tenants/${foreign.tenantId}/bots/${foreign.botId}`;
  for (const path of [
    `${other}/rag`,
    `${other}/rag/costs`,
    `${other}/tone-and-rules`,
  ])
    expect((await request.get(path)).status(), `GET ${path}`).toBe(404);
  expect(
    (
      await request.patch(`${other}/rag`, {
        headers,
        data: { tier: "premium" },
      })
    ).status(),
  ).toBe(404);
}

async function expectNoPlatformPages(page: Page) {
  for (const path of [
    "/platform",
    "/platform/operations",
    "/platform/bots",
    "/platform/members",
    "/platform/change-requests",
  ]) {
    await page.goto(path);
    await expect(page, path).not.toHaveURL(/\/platform(\/|$|#)/);
    await expect(page.getByTestId("organization-name")).toHaveCount(0);
    await expect(
      page.getByRole("heading", {
        name: /platform|operations|all organizations/i,
      }),
    ).toHaveCount(0);
  }
}

test("client admin requests a change and a separate operator triages it", async ({
  page,
  browser,
}) => {
  const { tenantId, botName } = await registerAdmin(page, "Change request");
  const bot = (
    await (await page.request.get(`/api/v1/tenants/${tenantId}/bots`)).json()
  )[0] as { id: string };
  await page.goto(`/app/${tenantId}/bots/${bot.id}/knowledge`);
  await expect(page).toHaveURL(`/app/${tenantId}`);
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
  await request
    .getByRole("combobox", { name: /^Status for / })
    .selectOption("triaged");
  await expect(request.getByText(/Status: triaged/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Status: triaged/)).toBeVisible();
  await page.goto(`/app/${tenantId}/analytics`);
  await expect(page.getByTestId("rag-operator-panel")).toHaveCount(0);
  await operator.goto(`/app/${tenantId}/analytics`);
  const aiPanel = operator.getByTestId("rag-operator-panel");
  await expect(aiPanel).toBeVisible();
  await aiPanel
    .getByRole("spinbutton", { name: "AI tokens per month", exact: true })
    .fill("12345");
  await aiPanel
    .getByRole("button", { name: "Save AI limits", exact: true })
    .click();
  await expect(aiPanel.getByText("AI limits saved.")).toBeVisible();
  const limits = await operator.request.get(
    `/api/v1/tenants/${tenantId}/bots/${bot.id}/rag`,
  );
  expect((await limits.json()).effective_limits.monthly_tokens).toBe(12345);
  await aiPanel.getByRole("button", { name: "Reset to plan defaults" }).click();
  await operator
    .getByRole("dialog", { name: "Reset to plan defaults?" })
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    aiPanel.getByRole("spinbutton", {
      name: "AI tokens per month",
      exact: true,
    }),
  ).toHaveValue("");
  await page.goto(`/app/${tenantId}/bots/${bot.id}/settings`);
  await expect(page.getByTestId("rag-tier-control")).toHaveCount(0);
  await operator.goto(`/app/${tenantId}/bots/${bot.id}/settings`);
  const tierPanel = operator.getByTestId("rag-tier-control");
  await expect(tierPanel.getByTestId("rag-retrieval-mode")).toHaveText(
    "hybrid",
  );
  await expect(tierPanel.getByTestId("rag-backfill-status")).toHaveText(
    "never run",
  );
  await tierPanel.getByLabel("Tier").selectOption("premium");
  await expect(tierPanel.getByText("AI tier saved.")).toBeVisible();
  const premium = await operator.request.get(
    `/api/v1/tenants/${tenantId}/bots/${bot.id}/rag`,
  );
  expect((await premium.json()).tier).toBe("premium");
  await operatorContext.close();
  expect(botName).toBeTruthy();
});

test("all client roles cannot obtain snippets or enter bot-control surfaces", async ({
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
  expect(adminBot.widget_locator).toBeNull();
  expect(adminBot.config).toEqual({});
  await page.goto(`/app/${tenantId}/bots/${botId}/overview`);
  await expect(page.getByTestId("nav-knowledge")).toHaveCount(0);
  await expect(page.getByTestId("nav-install")).toHaveCount(0);
  for (const surface of ["install", "knowledge"]) {
    await page.goto(`/app/${tenantId}/bots/${botId}/${surface}`);
    await expect(page).toHaveURL(`/app/${tenantId}`);
    await expect(page.getByTestId("install-snippet")).toHaveCount(0);
  }
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "chatbot_csrf",
  )!.value;
  // Tenant B (separate session) supplies a bot hidden from tenant A members.
  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  const other = await registerAdmin(otherPage, "Client roles B");
  const otherBots = (await (
    await otherPage.request.get(`/api/v1/tenants/${other.tenantId}/bots`)
  ).json()) as { id: string }[];
  const foreign = { tenantId: other.tenantId, botId: otherBots[0].id };
  await otherContext.close();
  const own = { tenantId, botId };
  // The tenant admin is a client role too: no staff-only API or page.
  await expectStaffOnlyDenied(page.request, csrf, own, foreign);
  await expectNoPlatformPages(page);
  await page.goto(`/app/${tenantId}/bots/${botId}/settings`);
  await expect(page).toHaveURL(`/app/${tenantId}`);
  for (const role of ["editor", "viewer"]) {
    const email = uniqueEmail(role);
    // S2: invitations target existing users; register the account first in an
    // isolated context so the admin session (shared jar) is not replaced.
    const regContext = await browser.newContext();
    expect(
      (
        await regContext.request.post("/api/v1/auth/register", {
          data: { email, password: "Str0ngPass!" },
        })
      ).status(),
    ).toBe(201);
    await regContext.close();
    const invited = await page.request.post(
      `/api/v1/tenants/${tenantId}/invitations`,
      { headers: { "X-CSRF-Token": csrf }, data: { email, role } },
    );
    expect(invited.status()).toBe(201);
    const link = (await invited.json()).link_path as string;
    const token = new URL(link, "http://localhost").searchParams.get("token")!;
    const context = await browser.newContext();
    const member = await context.newPage();
    // S2: invitations target existing users; sign in with the pre-registered
    // account and accept the invitation with that session.
    expect(
      (
        await member.request.post("/api/v1/auth/login", {
          data: { email, password: "Str0ngPass!" },
        })
      ).status(),
    ).toBe(200);
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
    await member.goto(`/app/${tenantId}/analytics`);
    await expect(member.getByTestId("rag-operator-panel")).toHaveCount(0);
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
    await member.goto(`/app/${tenantId}/bots/${botId}/settings`);
    await expect(member.getByTestId("rag-tier-control")).toHaveCount(0);
    expect(
      (
        await member.request.get(
          `/api/v1/tenants/${tenantId}/bots/${botId}/rag`,
        )
      ).status(),
    ).toBe(403);
    await expectStaffOnlyDenied(member.request, memberCsrf, own, foreign);
    await expectNoPlatformPages(member);
    await member.goto(`/app/${tenantId}/bots/${botId}/settings`);
    await expect(member).toHaveURL(`/app/${tenantId}`);
    await expect(member.getByTestId("tone-and-rules-section")).toHaveCount(0);
    await member.goto(`/app/${tenantId}/bots/${botId}/install`);
    await expect(member).toHaveURL(`/app/${tenantId}`);
    await expect(member.getByTestId("install-snippet")).toHaveCount(0);
    await member.goto(`/app/${tenantId}/bots/${botId}/knowledge`);
    await expect(member).toHaveURL(`/app/${tenantId}`);
    await expect(member.getByTestId("sources-list")).toHaveCount(0);
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
