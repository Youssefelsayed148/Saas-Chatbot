import { expect, test, type Page } from "@playwright/test";

/**
 * B4 dashboards with a fully mocked API (no database): chart presence and text
 * alternatives, previous-period deltas, the 7/30/90 day selector, hidden empty
 * cards, formatted rates, at-limit vs approaching wording, staff health alert.
 */

const tenant = "11111111-1111-4111-8111-111111111111";
const botId = "22222222-2222-4222-8222-222222222222";
const base = `/app/${tenant}`;
const botBase = `${base}/bots/${botId}`;

type Options = {
  staff?: boolean;
  empty?: boolean;
  modelFailing?: boolean;
  published?: boolean;
  atLimit?: string[];
};

function days(count: number) {
  const out = [];
  for (let index = 0; index < count; index += 1) {
    const day = new Date(Date.UTC(2026, 8, 1 + index))
      .toISOString()
      .slice(0, 10);
    out.push({
      day,
      conversations: index % 5,
      handoffs: index % 3 === 0 ? 1 : 0,
      resolved: index % 2,
    });
  }
  return out;
}

async function mock(page: Page, options: Options = {}) {
  const analyticsFrom: string[] = [];
  await page.route("**/api/v1/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1/", "");
    const respond = (json: unknown) => route.fulfill({ json });
    if (path === "auth/me")
      return respond({
        id: "b4-user",
        email: "b4@example.com",
        is_platform_staff: !!options.staff,
        memberships: options.staff
          ? []
          : [{ tenant_id: tenant, tenant_name: "B4 org", role: "admin" }],
      });
    if (path === "auth/config") return respond({ self_serve_signup: false });
    if (path === "platform/tenants")
      return respond({ tenants: [], total: 0 });
    const suffix = path.replace(`tenants/${tenant}`, "");
    if (suffix === "/bots")
      return respond([
        {
          id: botId,
          name: "Shop assistant",
          status: "active",
          config: {},
          widget_locator: null,
        },
      ]);
    if (suffix === `/bots/${botId}`)
      return respond({
        id: botId,
        name: "Shop assistant",
        status: "active",
        config: {},
        widget_locator: null,
      });
    if (suffix === "/quota")
      return respond({
        placeholder: true,
        plan: "business",
        warnings: ["monthly_messages", "contacts"],
        at_limit: options.atLimit ?? ["contacts"],
        usage: { bots: 1, monthly_messages: 85, contacts: 10 },
        limits: { bots: 2, monthly_messages: 100, contacts: 10 },
        measured_tokens_this_month: 1234,
      });
    if (suffix === "/inbox/counts")
      return respond({
        waiting_human: 2,
        assigned_to_me: 1,
        unread_messages: 4,
        unread_conversations: 3,
      });
    if (suffix === "/inbox")
      return respond({
        conversations: options.empty
          ? []
          : [
              {
                id: "c1",
                bot_id: botId,
                contact_id: null,
                contact_name: "مريم",
                channel: "website",
                mode: "ai",
                status: "open",
                assigned_user_id: null,
                handoff_reason: null,
                last_message: "هل لديكم توصيل؟",
                last_message_at: new Date(Date.now() - 3_600_000).toISOString(),
              },
            ],
        total: 1,
        limit: 5,
        offset: 0,
      });
    if (suffix === `/bots/${botId}/revisions`)
      return respond({
        revisions: [],
        published_revision_id: options.published ? "rev-1" : null,
      });
    if (suffix === `/bots/${botId}/readiness`)
      return respond({
        ready: !options.modelFailing,
        items: [
          {
            id: "model_reachable",
            label: "Recent model calls",
            status: options.modelFailing ? "warning" : "ok",
            detail: "Recent model calls failed.",
            section: "tier",
          },
        ],
      });
    if (suffix === "/analytics/timeseries")
      return respond({
        from: "2026-09-01",
        to: "2026-09-30",
        days: options.empty ? [] : days(30),
      });
    if (suffix === "/analytics") {
      analyticsFrom.push(url.searchParams.get("from") ?? "");
      return respond({
        total_conversations: options.empty ? 0 : 40,
        handoff_count: 8,
        handoff_rate: 0.2,
        average_first_human_reply_seconds: 90,
        conversations_by_channel: options.empty ? {} : { website: 40 },
        resolved_vs_open: options.empty
          ? { resolved: 0, open: 0 }
          : { resolved: 30, open: 10 },
        sentiment_distribution: options.empty
          ? {}
          : { positive: 10, neutral: 25, negative: 5 },
        agent_workload: {},
        previous: {
          from: "2026-08-01",
          to: "2026-08-30",
          total_conversations: 20,
          handoff_count: 4,
          handoff_rate: 0.2,
          average_first_human_reply_seconds: 120,
        },
      });
    }
    if (suffix.endsWith("/analytics/summary"))
      return respond({
        messages: 12,
        conversations: 4,
        widget_opens: 9,
        engagement_rate: 1,
        avg_messages_per_conversation: 3,
        message_distribution: { short: 3, long: 1 },
        fallback_rate: 0.25,
        cannot_answer: 1,
        needs_human: 0,
        handoffs: 0,
        avg_response_ms: 2408,
        leads: 1,
        thumbs_up: 0,
        thumbs_down: 0,
      });
    if (suffix.endsWith("/analytics/volume"))
      return respond({
        days: [
          { day: "2026-09-01", visitor: 3, assistant: 3 },
          { day: "2026-09-02", visitor: 2, assistant: 2 },
        ],
      });
    if (suffix.endsWith("/analytics/top-questions"))
      return respond({ questions: [{ question: "Opening hours?", asked: 5 }] });
    if (suffix.endsWith("/analytics/unanswered"))
      return respond({ questions: [] });
    if (suffix.endsWith("/analytics/leads"))
      return respond({ trend: [], contacts: [] });
    if (suffix === "/inbox/events")
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": fixture\n\n",
      });
    return respond([]);
  });
  return { analyticsFrom };
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

test("Overview: trend chart with a text alternative, donut, formatted recents, wording", async ({
  page,
}) => {
  await mock(page);
  await page.goto(base);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  const trend = page.getByRole("group", { name: "Conversations per day" });
  await expect(trend).toBeVisible();
  const table = trend.getByRole("table", { name: "Conversations per day" });
  await expect(table.getByRole("row")).toHaveCount(31);
  await expect(
    page.getByRole("group", { name: "Resolved and open conversations" }),
  ).toContainText("Resolved");
  await expect(page.getByText("Current inbox")).toHaveCount(0);
  await expect(page.getByText("+100%")).toBeVisible();
  const row = page.locator(".recent-list li").first();
  await expect(row).toContainText("مريم");
  await expect(row).toContainText("هل لديكم توصيل؟");
  await expect(row).toContainText(/open/i);
  await expect(row).toContainText("hour ago");
  await expect(row.locator("[dir='auto']").first()).toBeVisible();
  const plan = page.getByRole("region", { name: "Plan usage" });
  await expect(plan.getByRole("meter")).toHaveCount(2);
  await expect(plan).toContainText("Plan limit reached for Contacts");
  await expect(plan).toContainText(
    "Approaching the plan limit for Messages this month",
  );
  await expect(plan).not.toContainText(/provisional|Assistants/);
  await expect(page.getByTestId("rag-operator-panel")).toHaveCount(0);
  await expect(page.locator(".overview-alert")).toHaveCount(0);
});

test("Overview: no data hides chart cards; staff see health alert and unfinished checklist only", async ({
  page,
}) => {
  await mock(page, { empty: true, staff: true, modelFailing: true });
  await page.goto(base);
  await expect(page.locator(".overview-alert")).toContainText(
    "Recent model calls failed.",
  );
  await expect(page.getByText("Conversations over time")).toHaveCount(0);
  await expect(page.getByText("Outcomes", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Your first assistant")).toBeVisible();
  await expect(page.getByText(/Plan limits are provisional/)).toBeVisible();
});

test("Overview: finished checklist and healthy model are not shown", async ({
  page,
}) => {
  await mock(page, { staff: true, published: true });
  await page.goto(base);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Plan usage", { exact: true })).toBeVisible();
  await expect(page.getByText("Your first assistant")).toHaveCount(0);
  await expect(page.locator(".overview-alert")).toHaveCount(0);
});

test("Insights: period selector refetches, deltas and chart alternatives show", async ({
  page,
}) => {
  const { analyticsFrom } = await mock(page);
  await page.goto(`${base}/analytics`);
  await expect(
    page.getByRole("heading", { name: "Insights", exact: true }),
  ).toBeVisible();
  const outcomes = page.locator(".ui-card", {
    hasText: "Conversation outcomes",
  });
  await expect(outcomes).toContainText(/Conversations\s*40/);
  await expect(outcomes).toContainText("+100%");
  await expect(outcomes).toContainText("20%");
  await expect(outcomes).toContainText("1.5 min");
  await expect(
    page.getByRole("group", { name: "Resolved and open conversations" }),
  ).toBeVisible();
  await expect(
    page.getByRole("group", { name: "Conversation sentiment" }),
  ).toContainText("Neutral");
  await expect(page.getByText("Agent workload")).toHaveCount(0);
  const thirty = page.getByRole("button", { name: "30 days" });
  await expect(thirty).toHaveAttribute("aria-pressed", "true");
  const before = analyticsFrom.length;
  await page.getByRole("button", { name: "7 days" }).click();
  await expect(page.getByRole("button", { name: "7 days" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect.poll(() => analyticsFrom.length).toBeGreaterThan(before);
  const first = new Date(analyticsFrom[0]).getTime();
  const last = new Date(analyticsFrom.at(-1) ?? "").getTime();
  expect(Math.round((last - first) / 86_400_000)).toBe(23);
});

test("Insights: an empty period shows one message and no empty cards", async ({
  page,
}) => {
  await mock(page, { empty: true });
  await page.goto(`${base}/analytics`);
  await expect(page.getByText("No conversations in this period.")).toBeVisible();
  for (const title of [
    "Conversation outcomes",
    "Conversations by channel",
    "Sentiment",
  ])
    await expect(page.getByText(title, { exact: true })).toHaveCount(0);
});

test("Bot overview: percentages, seconds, volume chart, hidden thumbs tile", async ({
  page,
}) => {
  await mock(page);
  await page.goto(`${botBase}/overview`);
  const summary = page.getByTestId("overview-summary");
  await expect(summary.locator("[data-test='engagement']")).toContainText(
    "100%",
  );
  await expect(summary.locator("[data-test='fallback']")).toContainText("25%");
  await expect(summary.locator("[data-test='avg_response']")).toContainText(
    "2.4 s",
  );
  await expect(summary.locator("[data-test='thumbs']")).toHaveCount(0);
  await expect(summary).not.toContainText(/undefined|NaN|\bms\b/);
  const volume = page.getByTestId("volume");
  await expect(
    volume.getByRole("table", { name: "Messages per day" }),
  ).toHaveCount(1);
  await expect(page.getByTestId("top-questions")).toContainText(
    "Opening hours?",
  );
  await expect(page.getByTestId("top-questions").locator("li")).toHaveCount(1);
  await expect(page.getByTestId("unanswered")).toHaveCount(0);
  await expect(page.getByTestId("leads")).toHaveCount(0);
  await expect(page.getByTestId("export-conversations")).toHaveCount(1);
});
