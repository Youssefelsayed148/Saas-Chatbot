import { expect, test } from "@playwright/test";
import path from "node:path";
import { mkdirSync } from "node:fs";
import { registerAndPrepareBot } from "../tests/e2e-helpers";
import { promoteToStaff } from "../tests/staff-helpers";

// Default: desktop 1440 and mobile 360 (unchanged). For the design-system
// baseline set SCREENSHOT_VIEWPORTS=375,768,1280 (widths; height 900) and
// SCREENSHOT_DIR to an untracked folder.
const VIEWPORTS: [string, { width: number; height: number }][] = process.env
  .SCREENSHOT_VIEWPORTS
  ? process.env.SCREENSHOT_VIEWPORTS.split(",").map((w) => [
      `w${w.trim()}`,
      { width: Number(w), height: 900 },
    ])
  : [
      ["desktop", { width: 1440, height: 900 }],
      ["mobile", { width: 360, height: 800 }],
    ];

test("capture all redesigned pages in both themes and viewports", async ({
  page,
  browser,
}) => {
  test.setTimeout(600000);
  const { tenantId, botId, locator } = await registerAndPrepareBot(
    page,
    "Screenshots",
  );
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  promoteToStaff(me.email);
  const session = await (
    await page.request.post(`/api/public/v1/widgets/${locator}/sessions`, {
      data: { page_origin: null },
    })
  ).json();
  const headers = { "X-Session-Token": session.token };
  const turn = await (
    await page.request.post(
      `/api/public/v1/sessions/${session.session_id}/messages`,
      { headers, data: { text: "When are you open?" } },
    )
  ).json();
  const lead = await (
    await page.request.post(
      `/api/public/v1/sessions/${session.session_id}/lead`,
      {
        headers,
        data: {
          name: "زائر تجريبي · Demo visitor",
          email: "screenshot@example.com",
          phone: null,
          consent_accepted: true,
        },
      },
    )
  ).json();
  expect(turn.conversation_id).toBeTruthy();
  expect(lead.contact_id).toBeTruthy();
  const base = `/app/${tenantId}`;
  const bot = `${base}/bots/${botId}`;
  const routes: [string, string][] = [
    ["organizations", "/app"],
    ["tenant-overview", base],
    ["bots", `${base}/bots`],
    ...[
      "overview",
      "settings",
      "knowledge",
      "playground",
      "install",
      "conversations",
    ].map((tab) => [`bot-${tab}`, `${bot}/${tab}`] as [string, string]),
    ["bot-conversation", `${bot}/conversations/${turn.conversation_id}`],
    ["inbox", `${base}/inbox`],
    ["inbox-conversation", `${base}/inbox/${turn.conversation_id}`],
    ["contacts", `${base}/contacts`],
    ["contact-profile", `${base}/contacts/${lead.contact_id}`],
    ["handoff-analytics", `${base}/analytics`],
    ["team", `${base}/settings/members`],
    ["tenant-data", `${base}/settings/data`],
    ["platform-clients", "/platform"],
    ["platform-client", `/platform/clients/${tenantId}`],
    ["platform-operations", "/platform/operations"],
    ["widget-sample", `/widget/sample?locator=${locator}`],
    ["widget-frame", `/widget/frame?locator=${locator}`],
  ];
  const output = process.env.SCREENSHOT_DIR
    ? path.resolve(process.env.SCREENSHOT_DIR)
    : path.resolve(process.cwd(), "../../implementation/ui-screens");
  mkdirSync(output, { recursive: true });
  for (const [name, url] of routes) {
    for (const [viewport, size] of VIEWPORTS) {
      await page.setViewportSize(size);
      await page.goto(url);
      if (name === "widget-frame")
        await expect(page.getByTestId("widget-title")).not.toBeEmpty();
      else await expect(page.locator("main").first()).toBeVisible();
      if (url.startsWith(base)) {
        await expect(page.getByTestId("workspace-context")).toContainText(
          "admin",
        );
      }
      if (name === "widget-sample") {
        await expect(page.getByTestId("widget-bubble")).toBeVisible();
      }
      if (name === "tenant-data") {
        await expect(
          page.getByRole("button", { name: "Download export" }),
        ).toBeVisible();
      }
      await expect(page.locator(".loading-state")).toHaveCount(0, {
        timeout: 30000,
      });
      await page.evaluate(() => document.fonts.ready);
      for (const theme of ["dark", "light"]) {
        await page.evaluate(
          ({ theme, id }) => {
            localStorage.setItem(`chatbot-theme-${id}`, theme);
            document.documentElement.dataset.theme = theme;
          },
          { theme, id: me.id },
        );
        await page.screenshot({
          path: path.join(output, `${name}-${theme}-${viewport}.png`),
          fullPage: true,
          animations: "disabled",
        });
        if (name === "widget-sample") {
          await page.getByTestId("widget-bubble").click();
          const frame = page.frameLocator("[data-testid=widget-frame]");
          await expect(frame.getByTestId("widget-title")).not.toBeEmpty();
          await frame.locator("html").evaluate((element, theme) => {
            element.dataset.theme = theme;
          }, theme);
          await page.screenshot({
            path: path.join(output, `widget-embedded-${theme}-${viewport}.png`),
            fullPage: true,
            animations: "disabled",
          });
          await frame.getByTestId("widget-close").click();
        }
      }
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${name}/${viewport} horizontal overflow`,
      ).toBe(true);
    }
  }
  const anonymous = await browser.newContext();
  const auth = await anonymous.newPage();
  for (const [name, url] of [
    ["landing", "/"],
    ["login", "/login"],
    ["register", "/register"],
    ["accept-invite", "/accept-invite?token=preview"],
  ]) {
    for (const [viewport, size] of VIEWPORTS) {
      await auth.setViewportSize(size);
      await auth.goto(url);
      await expect(auth.locator("main").first()).toBeVisible();
      for (const theme of ["dark", "light"]) {
        await auth.evaluate((theme) => {
          localStorage.setItem("chatbot-theme-anonymous", theme);
          document.documentElement.dataset.theme = theme;
        }, theme);
        await auth.screenshot({
          path: path.join(output, `${name}-${theme}-${viewport}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
    }
  }
  await anonymous.close();
});
