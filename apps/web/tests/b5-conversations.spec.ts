import { expect, test, type Page } from "@playwright/test";

/**
 * B5 Conversations module (Inbox + History tabs) with a fully mocked API (no
 * database): shell and tab navigation, first row above the fold, filter chips,
 * tenant-wide History query + pagination, row delete, retention, viewer role.
 */

const tenant = "11111111-1111-4111-8111-111111111111";
const botId = "22222222-2222-4222-8222-222222222222";
const base = `/app/${tenant}`;
const botBase = `${base}/bots/${botId}`;
const ROW_COUNT = 60;
const PAGE_SIZE = 25;

type Role = "admin" | "viewer" | "staff";

function makeRows() {
  return Array.from({ length: ROW_COUNT }, (_, index) => ({
    id: `c${index + 1}`,
    bot_id: botId,
    contact_id: null,
    contact_name: `Visitor ${index + 1}`,
    created_at: new Date(
      Date.UTC(2026, 8, 1, 9, 0) + index * 60_000,
    ).toISOString(),
    channel: "website",
    mode: index % 2 ? "human" : "ai",
    status: index % 3 === 0 ? "waiting_human" : "open",
    assigned_user_id: null,
    handoff_reason: null,
    last_message_at: new Date(
      Date.UTC(2026, 8, 2, 9, 0) - index * 60_000,
    ).toISOString(),
    last_message: `Question number ${index + 1}`,
    unread_count: index % 4 === 0 ? 1 : 0,
    tags: [],
  }));
}

async function mock(page: Page, role: Role = "admin") {
  const rows = makeRows();
  const inboxQueries: URLSearchParams[] = [];
  const deletes: string[] = [];
  const patches: unknown[] = [];
  let retention: number | null = 30;
  let botListReads = 0;
  const staff = role === "staff";
  await page.route("**/api/v1/**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/", "");
    const respond = (json: unknown) => route.fulfill({ json });
    if (path === "auth/me")
      return respond({
        id: "b5-user",
        email: "b5@example.com",
        is_platform_staff: staff,
        memberships: staff
          ? []
          : [{ tenant_id: tenant, tenant_name: "B5 org", role }],
      });
    if (path === "auth/config") return respond({ self_serve_signup: false });
    if (path === "platform/tenants") return respond({ tenants: [], total: 0 });
    const suffix = path.replace(`tenants/${tenant}`, "");
    if (suffix === "/bots") {
      return respond([
        {
          id: botId,
          name: "Shop assistant",
          status: "active",
          config: {},
          widget_locator: null,
        },
      ]);
    }
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
        warnings: [],
        usage: {},
        limits: {},
        measured_tokens_this_month: 0,
      });
    if (suffix === "/inbox/counts")
      return respond({
        waiting_human: 2,
        assigned_to_me: 1,
        unread_messages: 4,
        unread_conversations: 3,
      });
    if (suffix === "/inbox/events")
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": fixture\n\n",
      });
    if (suffix === "/inbox") {
      inboxQueries.push(url.searchParams);
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return respond({
        conversations: rows.slice(offset, offset + limit),
        total: rows.length,
        limit,
        offset,
      });
    }
    if (suffix === "") {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON() as {
          retention_days: number | null;
        };
        patches.push(body);
        retention = body.retention_days;
      }
      return respond({
        id: tenant,
        name: "B5 org",
        slug: "b5",
        status: "active",
        retention_days: retention,
        created_at: "2026-09-01T00:00:00Z",
      });
    }
    const deleteMatch = suffix.match(/^\/bots\/[^/]+\/conversations\/([^/]+)$/);
    if (deleteMatch && request.method() === "DELETE") {
      deletes.push(deleteMatch[1]);
      return route.fulfill({ status: 200, json: { status: "deleted" } });
    }
    if (suffix === `/bots/${botId}/conversations`) {
      botListReads += 1;
      return respond({
        conversations: rows
          .filter((row) => !deletes.includes(row.id))
          .slice(0, 5)
          .map((row) => ({
            id: row.id,
            channel: row.channel,
            mode: row.mode,
            status: row.status,
            contact_name: row.contact_name,
            last_message_at: row.last_message_at,
            message_count: 2,
            created_at: row.created_at,
          })),
        total: ROW_COUNT - deletes.length,
      });
    }
    if (deleteMatch)
      return respond({
        conversation: {
          id: deleteMatch[1],
          channel: "website",
          mode: "ai",
          status: "open",
          contact_name: "Visitor",
          last_message_at: null,
          message_count: 1,
          created_at: "2026-09-01T09:00:00Z",
        },
        messages: [
          {
            id: "m1",
            sender_type: "visitor",
            text: "Saved question",
            citations: [],
            can_answer: null,
            needs_human: false,
            created_at: "2026-09-01T09:00:00Z",
          },
        ],
      });
    const thread = suffix.match(/^\/conversations\/([^/]+)$/);
    if (thread)
      return respond({
        conversation: {
          ...rows[0],
          id: thread[1],
          mode: "human",
          status: "open",
        },
        messages: [],
      });
    if (suffix.endsWith("/read")) return respond({ unread_count: 0 });
    return respond([]);
  });
  return {
    inboxQueries,
    deletes,
    patches,
    lastInbox: () => inboxQueries[inboxQueries.length - 1],
    botListReads: () => botListReads,
  };
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

function sidebar(page: Page) {
  return page
    .locator("aside")
    .getByRole("navigation", { name: "Workspace navigation" });
}

async function expectShell(page: Page, tab: "inbox" | "history") {
  await expect(
    page.getByRole("heading", { level: 1, name: "Conversations", exact: true }),
  ).toBeVisible();
  await expect(page.locator("main h1")).toHaveCount(1);
  const tablist = page.getByRole("tablist", { name: "Conversations sections" });
  await expect(tablist).toBeVisible();
  await expect(page.getByTestId("conversations-tab-inbox")).toHaveAttribute(
    "aria-selected",
    tab === "inbox" ? "true" : "false",
  );
  await expect(page.getByTestId("conversations-tab-history")).toHaveAttribute(
    "aria-selected",
    tab === "history" ? "true" : "false",
  );
  const current = sidebar(page).locator('[aria-current="page"]');
  await expect(current).toHaveCount(1);
  await expect(current).toHaveText(/Conversations/);
}

const shellRoutes: [string, string, "inbox" | "history"][] = [
  ["inbox", `${base}/inbox`, "inbox"],
  ["inbox thread", `${base}/inbox/c1`, "inbox"],
  ["tenant history", `${base}/conversations`, "history"],
  ["per-bot history", `${botBase}/conversations`, "history"],
  ["saved thread", `${botBase}/conversations/c1`, "history"],
];

for (const [name, path, tab] of shellRoutes) {
  test(`shell: ${name} renders the Conversations shell with the ${tab} tab and one active sidebar item`, async ({
    page,
  }) => {
    await mock(page);
    await page.goto(path);
    await expectShell(page, tab);
    await expect(sidebar(page).getByRole("link")).toContainText([
      /Overview/,
      /Conversations/,
    ]);
    // There is no separate sidebar Inbox item any more.
    await expect(
      sidebar(page).getByRole("link", { name: "Inbox", exact: true }),
    ).toHaveCount(0);
  });
}

test("shell: staff sidebar marks the single Conversations item on a per-bot history route", async ({
  page,
}) => {
  await mock(page, "staff");
  await page.goto(`${botBase}/conversations`);
  await expectShell(page, "history");
  await expect(sidebar(page).getByRole("link")).toHaveText([
    /Overview/,
    /Bots/,
    /Conversations/,
    /Contacts/,
    /Insights/,
    /Request a change/,
    /Team/,
    /Tenant data and audit/,
    /Platform admin/,
  ]);
});

test("tabs: Inbox and History tabs navigate to /inbox and /conversations", async ({
  page,
}) => {
  await mock(page);
  await page.goto(`${base}/inbox`);
  await expectShell(page, "inbox");
  await page.getByTestId("conversations-tab-history").click();
  await expect(page).toHaveURL(`${base}/conversations`);
  await expectShell(page, "history");
  await page.getByTestId("conversations-tab-inbox").click();
  await expect(page).toHaveURL(`${base}/inbox`);
  await expectShell(page, "inbox");
});

for (const size of [
  { width: 1920, height: 1140 },
  { width: 1280, height: 800 },
]) {
  test(`layout: first inbox row is visible without scrolling at ${size.width}x${size.height}`, async ({
    page,
  }) => {
    await mock(page);
    await page.setViewportSize(size);
    await page.goto(`${base}/inbox`);
    const first = page.getByTestId("inbox-list").getByRole("link").first();
    await expect(first).toBeVisible();
    await expect(first).toBeInViewport({ ratio: 1 });
    const box = await first.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(size.height);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
}

test("inbox: the list scrolls independently of the page", async ({ page }) => {
  await mock(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${base}/inbox`);
  const list = page.getByTestId("inbox-list");
  await expect(list.getByRole("link").first()).toBeVisible();
  expect(await list.evaluate((node) => node.scrollTop)).toBe(0);
  await list.evaluate((node) => {
    node.scrollTop = 300;
  });
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("inbox: filter chips update the URL, the request and aria-pressed; counts come from /inbox/counts", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${base}/inbox`);
  const chips = {
    waiting: page.getByTestId("inbox-filter-waiting"),
    mine: page.getByTestId("inbox-filter-mine"),
    unread: page.getByTestId("inbox-filter-unread"),
    all: page.getByTestId("inbox-filter-all"),
  };
  await expect(chips.all).toHaveAttribute("aria-pressed", "true");
  await expect(chips.waiting).toContainText("Waiting for a reply");
  await expect(chips.waiting).toContainText("2");
  await expect(chips.mine).toContainText("Assigned to me");
  await expect(chips.mine).toContainText("1");
  await expect(chips.unread).toContainText("Unread");

  const cases: [keyof typeof chips, string, string][] = [
    ["waiting", "status", "waiting_human"],
    ["mine", "assignee", "me"],
    ["unread", "unread", "true"],
  ];
  for (const [chip, param, value] of cases) {
    await chips[chip].click();
    await expect(page).toHaveURL(new RegExp(`[?&]${param}=${value}`));
    await expect.poll(() => api.lastInbox().get(param)).toBe(value);
    await expect(chips[chip]).toHaveAttribute("aria-pressed", "true");
    await expect(chips.all).toHaveAttribute("aria-pressed", "false");
    await chips.all.click();
    await expect(chips.all).toHaveAttribute("aria-pressed", "true");
    await expect(chips[chip]).toHaveAttribute("aria-pressed", "false");
    await expect
      .poll(() => {
        const query = api.lastInbox();
        return ["status", "assignee", "unread"].map((key) => query.has(key));
      })
      .toEqual([false, false, false]);
    await expect(page).not.toHaveURL(new RegExp(`[?&]${param}=`));
  }
});

test("inbox: More filters popover holds mode and closes with Escape; search is sent as q", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${base}/inbox`);
  await page.getByLabel("Search conversations").fill("refund");
  await expect.poll(() => api.lastInbox().get("q")).toBe("refund");
  await page.getByText("More filters", { exact: true }).click();
  await expect(page.getByTestId("inbox-mode-filter")).toBeVisible();
  await page.getByTestId("inbox-mode-filter").selectOption("human");
  await expect.poll(() => api.lastInbox().get("mode")).toBe("human");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("inbox-mode-filter")).not.toBeVisible();
});

test("history: search, status, channel and date range send q, status, channel, created_from, created_to", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${base}/conversations`);
  const table = page.getByTestId("conversations");
  await expect(table.locator("tbody tr").first()).toBeVisible();
  await expect(table).toContainText("Visitor 1");
  for (const column of [
    "Last activity",
    "Visitor",
    "Preview",
    "Status",
    "Channel",
  ])
    await expect(
      table.getByRole("columnheader", { name: column }),
    ).toBeVisible();
  await expect(
    table.getByRole("columnheader", { name: "Messages" }),
  ).toHaveCount(0);

  await page.getByLabel("Search history").fill("refund");
  await expect.poll(() => api.lastInbox().get("q")).toBe("refund");
  await page.getByRole("combobox", { name: "Status" }).selectOption("resolved");
  await expect.poll(() => api.lastInbox().get("status")).toBe("resolved");
  await page.getByRole("combobox", { name: "Channel" }).selectOption("website");
  await expect.poll(() => api.lastInbox().get("channel")).toBe("website");
  await page.getByLabel("From", { exact: true }).fill("2026-09-01");
  await expect
    .poll(() => api.lastInbox().get("created_from"))
    .toContain("2026-09-01");
  await page.getByLabel("To", { exact: true }).fill("2026-09-30");
  await expect
    .poll(() => api.lastInbox().get("created_to"))
    .toContain("2026-09-30");
  const url = new URL(page.url());
  expect(url.searchParams.get("q")).toBe("refund");
  expect(url.searchParams.get("status")).toBe("resolved");
  expect(url.searchParams.get("channel")).toBe("website");
  expect(url.searchParams.get("from")).toBe("2026-09-01");
  expect(url.searchParams.get("to")).toBe("2026-09-30");

  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect
    .poll(() => {
      const query = api.lastInbox();
      return ["q", "status", "channel", "created_from", "created_to"].map(
        (key) => query.has(key),
      );
    })
    .toEqual([false, false, false, false, false]);
});

test("history: 25 rows per page, total text, Previous disabled on page 1, offset 25 on page 2", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${base}/conversations`);
  const table = page.getByTestId("conversations");
  await expect(table.locator("tbody tr")).toHaveCount(PAGE_SIZE);
  expect(api.inboxQueries[0].get("limit")).toBe(String(PAGE_SIZE));
  expect(api.inboxQueries[0].get("offset") ?? "0").toBe("0");
  await expect(page.getByTestId("history-total")).toHaveText(
    `${ROW_COUNT} conversations`,
  );
  const pagination = page.getByTestId("history-pagination");
  await expect(pagination).toContainText("Page 1 of 3");
  await expect(
    pagination.getByRole("button", { name: "Previous page" }),
  ).toBeDisabled();
  await pagination.getByRole("button", { name: "Next page" }).click();
  await expect(pagination).toContainText("Page 2 of 3");
  await expect(page).toHaveURL(/[?&]page=2/);
  await expect.poll(() => api.lastInbox().get("offset")).toBe("25");
  expect(api.lastInbox().get("limit")).toBe(String(PAGE_SIZE));
  await expect(
    pagination.getByRole("button", { name: "Previous page" }),
  ).toBeEnabled();
  await expect(table).toContainText("Visitor 26");
});

test("history: a row opens the read-only saved thread under its bot", async ({
  page,
}) => {
  await mock(page);
  await page.goto(`${base}/conversations`);
  const row = page.getByTestId("conversations").locator("tbody tr").first();
  const link = row.getByRole("link").first();
  await expect(link).toHaveAttribute("href", `${botBase}/conversations/c1`);
  await link.click();
  await expect(page).toHaveURL(`${botBase}/conversations/c1`);
  await expect(page.getByTestId("conversation-thread")).toBeVisible();
  await expectShell(page, "history");
});

test("delete: row menu, Cancel leaves the row, Confirm sends DELETE and reloads the list", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${botBase}/conversations`);
  const table = page.getByTestId("conversations");
  await expect(table).toContainText("Visitor 1");
  const menu = page.getByTestId("row-menu-c1");
  await expect(menu).toHaveAttribute("aria-label", "More actions");
  await menu.click();
  await page.getByTestId("delete-c1").click();
  const dialog = page.getByRole("dialog", { name: "Delete conversation?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(api.deletes).toEqual([]);
  await expect(table).toContainText("Visitor 1");

  const readsBefore = api.botListReads();
  if (!(await page.getByTestId("delete-c1").isVisible())) await menu.click();
  await page.getByTestId("delete-c1").click();
  await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect.poll(() => api.deletes).toEqual(["c1"]);
  await expect.poll(() => api.botListReads()).toBeGreaterThan(readsBefore);
  await expect(table).not.toContainText("Visitor 1");
});

test("viewer: no row menu, delete or retention controls in the DOM; thread is read-only", async ({
  page,
}) => {
  await mock(page, "viewer");
  await page.goto(`${botBase}/conversations`);
  await expect(page.getByTestId("conversations")).toContainText("Visitor 1");
  await expect(page.locator('[data-testid^="row-menu-"]')).toHaveCount(0);
  await expect(page.locator('[data-testid^="delete-"]')).toHaveCount(0);
  await expect(page.locator('[data-testid^="retention-"]')).toHaveCount(0);
  await page.goto(`${base}/inbox/c1`);
  await expect(page.getByTestId("inbox-thread")).toBeVisible();
  for (const name of [
    "Take over",
    "Return to AI",
    "Resolve",
    "Send reply",
    "Add note",
  ])
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(
      0,
    );
  await expect(page.getByLabel("Reply", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Internal note", { exact: true })).toHaveCount(
    0,
  );
});

test("retention: summary shows the saved value, panel opens prefilled, invalid values send nothing, valid value PATCHes", async ({
  page,
}) => {
  const api = await mock(page);
  await page.goto(`${botBase}/conversations`);
  const panel = page.getByTestId("retention-panel");
  const summary = panel.locator("summary");
  await expect(summary).toContainText("Data retention");
  await expect(summary).toContainText("30");
  await summary.click();
  const input = page.getByTestId("retention-input");
  await expect(input).toBeVisible();
  await expect(input).toHaveValue("30");

  const type = await input.getAttribute("type");
  const invalid = [
    "",
    "0",
    "366",
    "1.5",
    ...(type === "number" ? [] : ["abc"]),
  ];
  for (const value of invalid) {
    await input.fill(value);
    await page.getByTestId("retention-save").click();
    await expect(
      panel.getByText("Enter a retention value between 1 and 365 days."),
    ).toBeVisible();
  }
  expect(api.patches).toEqual([]);

  await input.fill("90");
  await page.getByTestId("retention-save").click();
  await expect.poll(() => api.patches).toEqual([{ retention_days: 90 }]);
  await expect(page.getByTestId("retention-saved")).toBeVisible();
  await expect(summary).toContainText("90");
});
