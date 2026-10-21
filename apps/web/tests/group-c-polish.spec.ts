import { expect, test } from "@playwright/test";
import {
  safetyFixture,
  base,
  botBase,
  botId,
  tenant,
  conversationId,
  contactId,
  statuses,
} from "./group-c-fixtures";
import { promoteToStaff } from "./staff-helpers";
import { uniqueEmail } from "./e2e-helpers";

const confirmations = [
  {
    name: "member removal",
    path: `${base}/settings/members`,
    trigger: "Remove",
    title: "Remove member?",
    endpoint: `tenants/${tenant}/members/remove-user`,
    method: "DELETE",
    description: /lose access/,
  },
  {
    name: "conversation deletion",
    path: `${botBase}/conversations`,
    trigger: "Delete",
    title: "Delete conversation?",
    endpoint: `tenants/${tenant}/bots/${botId}/conversations/${conversationId}`,
    method: "DELETE",
    description: /permanently deleted/,
  },
  {
    name: "bot settings pause",
    path: `${botBase}/settings`,
    trigger: "Pause bot",
    title: "Pause bot?",
    endpoint: `tenants/${tenant}/bots/${botId}`,
    method: "PATCH",
    description: /stop answering/,
  },
  {
    name: "platform pause",
    path: `/platform/clients/${tenant}`,
    trigger: "Pause bot",
    title: "Pause bot?",
    endpoint: `platform/bots/${botId}/pause`,
    method: "POST",
    description: /stop answering/,
    platform: true,
  },
  {
    name: "embedding backfill",
    path: `${botBase}/settings`,
    trigger: "Start embedding backfill",
    title: "Start embedding backfill?",
    endpoint: `tenants/${tenant}/bots/${botId}/rag/backfill`,
    method: "POST",
    description: /incur provider costs/,
  },
  {
    name: "plan default reset",
    path: `${base}/analytics`,
    trigger: "Reset to plan defaults",
    title: "Reset to plan defaults?",
    endpoint: `tenants/${tenant}/bots/${botId}/rag`,
    method: "PATCH",
    description: /overrides.*removed/,
  },
];

for (const item of confirmations) {
  test(`${item.name}: Cancel and Escape do not write; Confirm writes once`, async ({
    page,
  }) => {
    const state = await safetyFixture(page, item.platform);
    await page.goto(item.path);
    if (item.platform) {
      await page.getByRole("tab", { name: "Bots", exact: true }).click();
      await page
        .getByLabel("Reason", { exact: true })
        .fill("Owner requested pause");
    }
    const trigger = page.getByRole("button", {
      name: item.trigger,
      exact: true,
    });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: item.title, exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(item.description);
    await expect(
      dialog.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    expect(state.writes).toEqual([]);
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    expect(state.writes).toEqual([]);
    await trigger.click();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    expect(state.writes).toEqual([]);
    await trigger.click();
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect.poll(() => state.writes.length).toBe(1);
    expect(state.writes[0]).toMatchObject({
      path: item.endpoint,
      method: item.method,
    });
    expect(state.unexpected).toEqual([]);
  });
}

test("both job lists show Retry only for failed and Cancel only for queued/running", async ({
  page,
}) => {
  const state = await safetyFixture(page, true);
  for (const path of [`${botBase}/knowledge`, "/platform/operations"]) {
    await page.goto(path);
    for (const status of statuses) {
      const row = path.includes("knowledge")
        ? page.locator(`[data-job-status="${status}"]`)
        : page
            .getByRole("row")
            .filter({ has: page.locator(`[data-status="${status}"]`) });
      await expect(row).toBeVisible();
      await expect(
        row.getByRole("button", { name: "Retry", exact: true }),
      ).toHaveCount(status === "failed" ? 1 : 0);
      await expect(
        row.getByRole("button", { name: "Cancel", exact: true }),
      ).toHaveCount(["pending", "running"].includes(status) ? 1 : 0);
    }
  }
  expect(state.unexpected).toEqual([]);
});

test("all audit views render historical owner and current admin actions", async ({
  page,
}) => {
  const state = await safetyFixture(page, true);
  for (const [path, region] of [
    [`${base}/settings/data`, "Tenant audit review"],
    ["/platform/operations", "Audit review"],
    [`/platform/clients/${tenant}`, "Recent audit"],
  ]) {
    await page.goto(path);
    const audit = page.getByRole("region", { name: region, exact: true });
    await expect(audit.getByText(/Admin invited/)).toHaveCount(2);
    await expect(audit.getByText(/Admin assigned/)).toHaveCount(2);
    await expect(audit).not.toContainText("owner_");
  }
  expect(state.unexpected).toEqual([]);
});

test("titles update on navigation; change requests use an SVG; contact dropdown has real middle dots", async ({
  page,
}) => {
  const state = await safetyFixture(page, true);
  for (const [path, title] of [
    [`${base}/inbox`, "Inbox"],
    [`${base}/contacts/${contactId}`, "Contact details"],
    [`${base}/settings/members`, "Team"],
    [`${botBase}/settings`, "Bot settings"],
    ["/platform/operations", "Platform operations"],
    [`/platform/clients/${tenant}`, "Organization details"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveTitle(`${title} · Website Chatbot SaaS`);
    await expect(page.locator("head title")).toHaveCount(1);
  }
  const change = page
    .getByRole("link", { name: "Change requests", exact: true })
    .first();
  await expect(change.locator("svg")).toHaveCount(1);
  await change.click();
  await expect(page).toHaveTitle("Change requests · Website Chatbot SaaS");
  await page.goto(`${base}/contacts/${contactId}`);
  await expect(
    page.getByLabel("Conversation", { exact: true }).locator("option").last(),
  ).toContainText("website · open ·");
  await expect(
    page.getByLabel("Conversation", { exact: true }),
  ).not.toContainText("\u00c2");
  const request = page
    .getByRole("link", { name: "Request a change", exact: true })
    .first();
  await expect(request.locator("svg")).toHaveCount(1);
  await request.click();
  await expect(page).toHaveTitle("Request a change · Website Chatbot SaaS");
  expect(state.unexpected).toEqual([]);
});

test("Save settings applies appearance live with no publication control", async ({
  page,
}) => {
  const state = await safetyFixture(page);
  await page.goto(`${botBase}/settings`);
  await expect(
    page.getByText(/Save settings applies appearance changes live/),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /publish/i })).toHaveCount(0);
  await page.getByLabel("Widget colour (hex, e.g. #1a2b3c)").fill("#123456");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0]).toMatchObject({
    method: "PATCH",
    body: { config: { colour: "#123456" } },
  });
});

test("favicon is a served ICO and sample page is protected by server staff access", async ({
  page,
}) => {
  const icon = await page.request.get("/favicon.ico");
  expect(icon.status()).toBe(200);
  expect((await icon.body()).subarray(0, 4)).toEqual(Buffer.from([0, 0, 1, 0]));
  await page.goto("/widget/sample?locator=private-check");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByTestId("sample-snippet")).toHaveCount(0);
  const email = uniqueEmail("sample-admin");
  expect(
    (
      await page.request.post("/api/v1/auth/register", {
        data: { email, password: "Str0ngPass!" },
      })
    ).status(),
  ).toBe(201);
  const csrf = (await page.context().cookies()).find(
    (c) => c.name === "chatbot_csrf",
  )!.value;
  expect(
    (
      await page.request.post("/api/v1/tenants", {
        headers: { "X-CSRF-Token": csrf },
        data: { name: "Sample admin org" },
      })
    ).status(),
  ).toBe(201);
  await page.goto("/widget/sample?locator=private-check");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByTestId("sample-snippet")).toHaveCount(0);
  promoteToStaff(email);
  await page.goto("/widget/sample?locator=private-check");
  await expect(page.getByTestId("sample-snippet")).toContainText(
    "private-check",
  );
  await expect(page).toHaveTitle("Widget sample · Website Chatbot SaaS");
});
