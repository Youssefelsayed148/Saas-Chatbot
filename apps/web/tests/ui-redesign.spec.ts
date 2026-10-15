import { expect, test } from "@playwright/test";
import { registerOwner } from "./e2e-helpers";

test("Arabic inbox rows preserve unread markers and removable filter requests", async ({
  page,
}) => {
  const { tenantId } = await registerOwner(page, "Arabic inbox");
  await page.route(`**/api/v1/tenants/${tenantId}/inbox?**`, (route) =>
    route.fulfill({
      json: {
        conversations: [
          {
            id: "arabic-row",
            contact_id: null,
            bot_id: "bot",
            channel: "website",
            mode: "ai",
            status: "waiting_human",
            last_message: "مرحبا، أحتاج مساعدة في حسابي",
            last_message_at: "2026-10-15T09:00:00Z",
            unread_count: 3,
            tags: ["عاجل"],
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    }),
  );
  await page.goto(`/app/${tenantId}/inbox?status=waiting_human`);
  const row = page.getByTestId("inbox-list").getByRole("link").first();
  await expect(row.locator(".message-snippet")).toHaveAttribute("dir", "auto");
  await expect(row.getByLabel("3 unread")).toBeVisible();
  await expect(row.locator("[data-value=waiting_human]")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove status filter" }),
  ).toBeVisible();
  await page.getByText("More filters", { exact: true }).click();
  const modeRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname.endsWith("/inbox") &&
      new URL(request.url()).searchParams.get("mode") === "human",
  );
  await page.getByLabel("Mode").selectOption("human");
  await modeRequest;
  await expect(
    page.getByRole("button", { name: "Remove mode filter" }),
  ).toBeVisible();
  await page.getByLabel("Mode").press("Escape");
  await expect(page.getByLabel("Mode")).not.toBeVisible();
  await page.getByRole("button", { name: "Remove mode filter" }).click();
  const cleared = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname.endsWith("/inbox") &&
      !new URL(request.url()).searchParams.has("status"),
  );
  await page.getByRole("button", { name: "Remove status filter" }).click();
  await cleared;
});

test("tenant Overview reads existing data and keeps Bots as the signup destination", async ({
  page,
}) => {
  const { tenantId } = await registerOwner(page, "Overview route");
  await expect(page).toHaveURL(`/app/${tenantId}/bots`);
  const writes: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PATCH", "DELETE"].includes(request.method()))
      writes.push(request.url());
  });
  await page.goto(`/app/${tenantId}`);
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("First bot created", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/final pricing and limits are TBD/),
  ).toBeVisible();
  expect(writes).toEqual([]);
});

test("workspace theme persists and keyboard palette only navigates", async ({
  page,
}) => {
  const { tenantId } = await registerOwner(page, "Shell");
  await expect(page.getByTestId("workspace-context")).toContainText("owner");
  const before = await page.locator("html").getAttribute("data-theme");
  await page.getByTestId("theme-toggle").first().click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    before === "dark" ? "light" : "dark",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    before === "dark" ? "light" : "dark",
  );
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Go to a page" });
  await expect(palette).toBeVisible();
  await palette.getByLabel("Search pages", { exact: true }).fill("Inbox");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/app/${tenantId}/inbox`);
  await expect(palette).not.toBeVisible();
});

test("mobile navigation opens and dismisses with Escape", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await registerOwner(page, "Mobile");
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", {
    name: "Workspace navigation",
    exact: true,
  });
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
