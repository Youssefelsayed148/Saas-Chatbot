import { expect, test, type Page } from "@playwright/test";
import type { Contact, Role } from "../lib/api";

const tenant = "11111111-1111-4111-8111-111111111111";
const botId = "22222222-2222-4222-8222-222222222222";
const conversationId = "33333333-3333-4333-8333-333333333333";
const base = `/app/${tenant}`;
const botBase = `${base}/bots/${botId}`;
const now = "2026-10-17T09:00:00Z";
const contact: Contact = {
  id: "44444444-4444-4444-8444-444444444444",
  display_name: "Visibility contact",
  email: "visitor@example.com",
  phone: null,
  stage: "new",
  tags: [],
  custom_fields: {},
  consent: {},
  source_channel: "website",
  created_at: now,
  updated_at: now,
};
const conversation = {
  id: conversationId,
  bot_id: botId,
  contact_id: contact.id,
  channel: "website",
  mode: "human",
  status: "open",
  assigned_user_id: null,
  handoff_reason: null,
  tags: [],
  last_message: "Hello",
  last_message_at: now,
  unread_count: 1,
  contact_name: contact.display_name,
  message_count: 1,
  created_at: now,
};
const counts = {
  waiting_human: 0,
  assigned_to_me: 0,
  unread_messages: 1,
  unread_conversations: 1,
};

async function fixture(page: Page, role: Role | "staff", hasBot = true) {
  const staff = role === "staff";
  const requests: string[] = [];
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname.replace(
      "/api/v1/",
      "",
    );
    requests.push(path);
    const respond = (json: unknown) => route.fulfill({ json });
    if (path === "auth/me")
      return respond({
        id: "visibility-user",
        email: "fixture@example.com",
        is_platform_staff: staff,
        memberships: staff
          ? []
          : [{ tenant_id: tenant, tenant_name: "Visibility org", role }],
      });
    if (path === "auth/config") return respond({ self_serve_signup: false });
    if (path === "platform/tenants")
      return respond({
        tenants: [{ id: tenant, name: "Visibility org", status: "active" }],
        total: 1,
      });
    const suffix = path.replace(`tenants/${tenant}`, "");
    if (suffix === "/bots")
      return respond(
        hasBot
          ? [
              {
                id: botId,
                name: "Operator assistant",
                status: "active",
                config: {},
                widget_locator: staff ? "fixture-locator" : null,
              },
            ]
          : [],
      );
    if (suffix === `/bots/${botId}`)
      return respond({
        id: botId,
        name: "Operator assistant",
        status: "active",
        config: {},
        widget_locator: "fixture-locator",
      });
    if (suffix === "/quota")
      return respond({
        placeholder: true,
        plan: "business",
        warnings: ["monthly_messages"],
        usage: {
          bots: 1,
          seats: 3,
          pages_per_bot: 5,
          upload_file_mb: 0,
          monthly_messages: 80,
          contacts: 1,
        },
        limits: {
          bots: 2,
          seats: 10,
          pages_per_bot: 100,
          upload_file_mb: 25,
          monthly_messages: 100,
          contacts: 500,
        },
        measured_tokens_this_month: 1234,
      });
    if (suffix === "/inbox/counts") return respond(counts);
    if (suffix === "/inbox/events")
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": fixture\n\n",
      });
    if (suffix === "/inbox" || suffix === `/bots/${botId}/conversations`)
      return respond({
        conversations: [conversation],
        total: 1,
        limit: 50,
        offset: 0,
      });
    if (suffix === `/conversations/${conversationId}`)
      return respond({ conversation, messages: [] });
    if (suffix.endsWith("/read")) return respond({ unread_count: 0 });
    if (suffix === "/contacts") return respond({ contacts: [contact] });
    if (suffix === `/contacts/${contact.id}`)
      return respond({
        contact,
        identities: [],
        timeline: [
          {
            type: "conversation",
            id: conversationId,
            channel: "website",
            status: "open",
            created_at: now,
          },
        ],
      });
    if (suffix === "/follow-ups") return respond({ follow_ups: [] });
    if (suffix === "/analytics")
      return respond({
        total_conversations: 1,
        handoff_count: 0,
        handoff_rate: 0,
        average_first_human_reply_seconds: null,
        conversations_by_channel: { website: 1 },
        resolved_vs_open: { resolved: 0, open: 1 },
        sentiment_distribution: {},
        agent_workload: {},
      });
    if (suffix.endsWith("/analytics/summary"))
      return respond({ message_distribution: {} });
    if (suffix.endsWith("/analytics/volume")) return respond({ days: [] });
    if (/\/analytics\/(top-questions|unanswered)$/.test(suffix))
      return respond({ questions: [] });
    if (suffix.endsWith("/analytics/leads"))
      return respond({ trend: [], contacts: [] });
    if (suffix.endsWith("/revisions"))
      return respond({ revisions: [], published_revision_id: null });
    if (suffix.endsWith("/documents")) return respond([]);
    if (suffix.endsWith("/rag"))
      return respond({
        tier: "standard",
        limits: {},
        effective_limits: {},
        usage: {},
      });
    if (suffix === "/data/audit") return respond({ events: [] });
    if (suffix === "")
      return respond({
        id: tenant,
        name: "Visibility org",
        retention_days: 30,
      });
    return respond([]);
  });
  return requests;
}

async function noOperatorText(page: Page) {
  // Include hidden drawer/palette DOM text, excluding executable hydration data.
  const text = await page.locator("body").evaluate((body) => {
    const clone = body.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("script, style").forEach((node) => node.remove());
    return clone.textContent;
  });
  expect(text).not.toMatch(
    /\bbots?\b|knowledge|playground|\binstall\b|\bdomains?\b|appearance|AI tier|AI costs?|AI limits|provisional|under review|platform staff|staff access|operator assistant/i,
  );
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

for (const role of ["admin", "editor", "viewer", "staff"] as const) {
  test(`${role}: navigation, client DOM, exports and action controls match API roles`, async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const requests = await fixture(page, role);
    const admin = role === "admin" || role === "staff";
    const edit = role !== "viewer";
    const inboxEdit = role === "admin" || role === "editor";
    const client = role !== "staff";
    const checkText = async () => {
      if (client) await noOperatorText(page);
    };
    await page.goto(base);
    const plan = page.getByRole("region", { name: "Plan usage", exact: true });
    await expect(plan).toContainText("business");
    await expect(plan).toContainText("Content pages");
    await expect(plan).toContainText("Maximum file size (MB)");
    await expect(plan.locator("input, select, button, a")).toHaveCount(0);
    await expect(
      plan.getByRole("progressbar", {
        name: "Messages this month",
        exact: true,
      }),
    ).toHaveAttribute("value", "80");
    await checkText();
    const nav = page
      .locator("aside")
      .getByRole("navigation", { name: "Workspace navigation" });
    const expected = [
      "Overview",
      client ? "Conversations" : "Bots",
      "Inbox",
      "Contacts",
      "Insights",
      ...(admin ? ["Request a change", "Team", "Tenant data and audit"] : []),
      ...(client ? [] : ["Platform admin"]),
    ];
    await expect(nav.getByRole("link")).toHaveText(
      expected.map((label) => new RegExp(label)),
    );
    if (client) {
      await expect(
        nav.getByRole("link", { name: "Conversations", exact: true }),
      ).toHaveAttribute("href", `${botBase}/conversations`);
      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: "Go to a page" });
      await expect(palette.getByRole("option")).toHaveCount(expected.length);
      await noOperatorText(page);
      await page.keyboard.press("Escape");
    }
    await page.goto(`${botBase}/conversations`);
    await expect(page.getByTestId("conversations")).toContainText(
      "Visibility contact",
    );
    await expect(page.getByTestId("retention-save")).toHaveCount(admin ? 1 : 0);
    await expect(page.getByTestId(`delete-${conversationId}`)).toHaveCount(
      admin ? 1 : 0,
    );
    await checkText();
    await page.goto(`${botBase}/overview`);
    await expect(page.getByTestId("overview-summary")).toBeVisible();
    await expect(page.getByTestId("export-conversations")).toHaveCount(
      admin ? 1 : 0,
    );
    await expect(page.getByTestId("export-leads")).toHaveCount(admin ? 1 : 0);
    await checkText();
    await page.goto(`${base}/contacts`);
    await expect(
      page.getByRole("link", { name: "Visibility contact", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Export CSV", exact: true }),
    ).toHaveCount(admin ? 1 : 0);
    await expect(
      page.getByRole("button", { name: "Create contact", exact: true }),
    ).toHaveCount(edit ? 1 : 0);
    await checkText();
    await page.goto(`${base}/contacts/${contact.id}`);
    await expect(
      page.getByRole("heading", { name: "Visibility contact", exact: true }),
    ).toBeVisible();
    for (const name of ["Save contact", "Schedule follow-up"])
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
        edit ? 1 : 0,
      );
    for (const name of ["Merge into selected contact", "Erase contact"])
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
        admin ? 1 : 0,
      );
    await checkText();
    await page.goto(`${base}/inbox/${conversationId}`);
    await expect(page.getByTestId("inbox-status")).toHaveText("Open");
    for (const name of ["Send reply", "Return to AI", "Resolve", "Add note"])
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
        inboxEdit ? 1 : 0,
      );
    await expect(
      page.getByRole("combobox", { name: "Assignee", exact: true }),
    ).toHaveCount(inboxEdit ? 1 : 0);
    await expect(page.getByLabel("Add tag", { exact: true })).toHaveCount(
      inboxEdit ? 1 : 0,
    );
    await checkText();
    await page.goto(`${base}/analytics`);
    await expect(
      page.getByRole("heading", { name: "Conversation outcomes", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("rag-operator-panel")).toHaveCount(
      client ? 0 : 1,
    );
    await checkText();
    if (role === "admin") {
      for (const pagePath of ["requests", "members", "data"]) {
        await page.goto(`${base}/settings/${pagePath}`);
        await expect(page.locator("main h1")).toBeVisible();
        await checkText();
      }
    }
    if (client) {
      for (const surface of [
        "knowledge",
        "install",
        "playground",
        "settings",
      ]) {
        await page.goto(`${botBase}/${surface}`);
        await expect(page).toHaveURL(base);
        await expect(
          page.getByRole("heading", { name: "Overview", exact: true }),
        ).toBeVisible();
        await checkText();
      }
      await page.goto(`${base}/bots`);
      await expect(page).toHaveURL(base);
      expect(
        requests.filter((path) =>
          /\/(sources|jobs|documents|revisions|playground|rag)(\/|$)/.test(
            path,
          ),
        ),
      ).toEqual([]);
    } else {
      await page.goto(`${botBase}/settings`);
      await expect(
        page.getByRole("button", { name: "Save settings", exact: true }),
      ).toBeVisible();
      await expect(page.getByLabel("Allowed domains")).toBeVisible();
      await expect(page.getByTestId("rag-tier-control")).toBeVisible();
      for (const tab of ["knowledge", "playground", "settings", "install"])
        await expect(page.getByTestId(`nav-${tab}`)).toBeVisible();
      await page.goto(`${botBase}/install`);
      await expect(page.getByTestId("install-snippet")).toContainText(
        "fixture-locator",
      );
    }
    expect(errors).toEqual([]);
  });
}

test("client with no current assistant has a Conversations empty state", async ({
  page,
}) => {
  await fixture(page, "viewer", false);
  await page.goto(`${base}/conversations`);
  await expect(
    page.getByText("No conversations available yet.", { exact: true }),
  ).toBeVisible();
  await noOperatorText(page);
});

test("restricted URL renders no shell while the client session is unresolved", async ({
  page,
}) => {
  await fixture(page, "editor");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/auth/me", async (route) => {
    await pending;
    await route.fallback();
  });
  try {
    await page.goto(`${botBase}/settings`);
    await expect(
      page.locator(".app-shell, main, [data-testid=rag-tier-control]"),
    ).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page).toHaveURL(base);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await noOperatorText(page);
});
