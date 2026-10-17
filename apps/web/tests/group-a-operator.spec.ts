import { expect, test, type Page } from "@playwright/test";

const tenantId = "11111111-1111-4111-8111-111111111111";
const conversationId = "22222222-2222-4222-8222-222222222222";

async function session(page: Page, staff: boolean, memberships: object[] = []) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "operator-fixture",
        email: "fixture@example.com",
        is_platform_staff: staff,
        memberships,
      },
    }),
  );
  await page.route("**/api/v1/auth/config", (route) =>
    route.fulfill({ json: { self_serve_signup: false } }),
  );
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

test("staff /app and switcher load every org without memberships", async ({
  page,
}) => {
  await session(page, true);
  await page.route(`**/api/v1/tenants/${tenantId}/bots*`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`**/api/v1/tenants/${tenantId}/quota`, (route) =>
    route.fulfill({
      json: {
        placeholder: true,
        plan: "starter",
        usage: {},
        limits: {},
        warnings: [],
        measured_tokens_this_month: 0,
      },
    }),
  );
  const organizations = Array.from({ length: 201 }, (_, i) => ({
    id: i === 0 ? tenantId : `org-${i}`,
    name: `Client ${i}`,
    slug: `client-${i}`,
    status: i === 200 ? "archived" : "active",
    plan_label: "starter",
    bots: 2,
    seats: 1,
    messages_this_month: 0,
    last_activity: i === 0 ? "2026-10-17T10:00:00Z" : null,
  }));
  const offsets: string[] = [];
  await page.route("**/api/v1/platform/tenants?*", (route) => {
    const params = new URL(route.request().url()).searchParams;
    offsets.push(params.get("offset")!);
    const offset = Number(params.get("offset"));
    return route.fulfill({
      json: { tenants: organizations.slice(offset, offset + 200), total: 201 },
    });
  });
  await page.goto("/app");
  const table = page.getByRole("table", { name: "All organizations" });
  await expect(table.locator("tbody tr")).toHaveCount(201);
  expect(offsets).toEqual(["0", "200"]);
  await expect(table.getByRole("row").first()).toContainText("Last activity");
  await expect(table.getByRole("row").nth(1)).toContainText("starter");
  await expect(table.getByRole("row").nth(1)).toContainText("active");
  const switcher = page.getByRole("combobox", {
    name: "Organization selector",
  });
  await expect(switcher.locator("option")).toHaveCount(202);
  await expect(switcher.locator("option").last()).toHaveText("Client 200");
  await expect(
    page.getByText("Your account needs an invitation to join an organization."),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Create / Onboard organization" }),
  ).toHaveAttribute("href", "/platform#onboard-client");
  await expect(
    page.getByRole("link", { name: "Open Client 0", exact: true }),
  ).toHaveAttribute("href", `/app/${tenantId}`);
  await expect(
    page.getByRole("link", { name: "Open Client 200", exact: true }),
  ).toHaveAttribute("href", "/platform/clients/org-200");
  await switcher.selectOption(tenantId);
  await expect(page).toHaveURL(`/app/${tenantId}/bots`);
  await expect(page.getByText("No bots yet.", { exact: true })).toBeVisible();
});

test("non-staff /app keeps invitation empty state and membership switcher", async ({
  page,
}) => {
  let platformRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/platform/tenants")) platformRequests++;
  });
  await session(page, false);
  await page.goto("/app");
  await expect(
    page.getByText("Your account needs an invitation to join an organization."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your organizations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "All organizations" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Create / Onboard organization" }),
  ).toHaveCount(0);
  await session(page, false, [
    {
      tenant_id: tenantId,
      tenant_name: "Client membership",
      tenant_slug: "client-membership",
      role: "admin",
    },
  ]);
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Client membership", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("combobox", { name: "Organization selector" })
      .locator("option"),
  ).toHaveCount(2);
  expect(platformRequests).toBe(0);
});

for (const withMembership of [false, true]) {
  test(`staff inbox is read-only (membership: ${withMembership})`, async ({
    page,
  }) => {
    await session(
      page,
      true,
      withMembership
        ? [{ tenant_id: tenantId, tenant_name: "Client", role: "admin" }]
        : [],
    );
    await page.route("**/api/v1/platform/tenants?*", (route) =>
      route.fulfill({ json: { tenants: [], total: 0 } }),
    );
    await page.route(`**/api/v1/tenants/${tenantId}/**`, (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith(`/conversations/${conversationId}`))
        return route.fulfill({
          json: {
            conversation: {
              id: conversationId,
              tenant_id: tenantId,
              bot_id: "bot",
              contact_id: null,
              mode: "human",
              status: "open",
              channel: "website",
              assigned_user_id: null,
              handoff_reason: null,
              last_message_at: null,
              tags: [],
            },
            messages: [],
            contact: null,
          },
        });
      if (path.endsWith("/inbox/counts"))
        return route.fulfill({
          json: {
            waiting_human: 0,
            assigned_to_me: 0,
            unread_messages: 0,
            unread_conversations: 0,
          },
        });
      if (path.endsWith("/inbox/events"))
        return route.fulfill({
          contentType: "text/event-stream",
          body: ": fixture\n\n",
        });
      return route.fulfill({
        json: path.endsWith("/inbox")
          ? { conversations: [], total: 0, limit: 50, offset: 0 }
          : [],
      });
    });
    const writes: string[] = [];
    page.on("request", (request) => {
      if (request.method() !== "GET") writes.push(request.url());
    });
    await page.goto(`/app/${tenantId}/inbox/${conversationId}`);
    await expect(
      page.getByText(
        "Staff view is read-only; replies come from client team members",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "Reply", exact: true }),
    ).toHaveCount(0);
    for (const name of [
      "Send reply",
      "Take over",
      "Return to AI",
      "Resolve",
      "Add note",
    ]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
        0,
      );
    }
    expect(writes).toEqual([]);
  });
}
