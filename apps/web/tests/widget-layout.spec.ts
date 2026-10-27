import { expect, type FrameLocator, type Page, test } from "@playwright/test";
import { registerStaffSession } from "./e2e-helpers";

/**
 * R3c-7 (#113): the open widget panel keeps a bounded height, the message list
 * scrolls inside it, the composer is never clipped and the "Contact us"
 * sheet opens and closes without squeezing the composer out.
 *
 * Network edge only: the config, session, history and message endpoints are
 * mocked, the stream endpoint answers 502 so the widget takes its single
 * buffered fallback (deterministic replies, no model).
 */

const LOCATOR = "layout";

const LAYOUTS = [
  {
    name: "desktop 1920x1140",
    viewport: { width: 1920, height: 1140 },
    lang: "en",
    dir: "ltr",
  },
  {
    name: "phone 375x667",
    viewport: { width: 375, height: 667 },
    lang: "en",
    dir: "ltr",
  },
  {
    name: "desktop RTL (Arabic)",
    viewport: { width: 1280, height: 800 },
    lang: "ar",
    dir: "rtl",
  },
] as const;

async function mockWidget(page: Page, lang: string, dir: string) {
  const config = {
    bot_name: "Layout bot",
    assistant_name: "Aida",
    business_name: "Acme",
    welcome_message: { en: "Hello there", ar: "أهلاً بك" },
    opening_questions: [],
    colour: "#123456",
    position: "right",
    default_language: lang,
    dir,
  };
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/config`, (route) =>
    route.fulfill({ json: { available: true, config } }),
  );
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/sessions`, (route) =>
    route.fulfill({
      status: 201,
      json: {
        session_id: "11111111-1111-4111-8111-111111111111",
        token: "tok",
        expires_at: new Date(Date.now() + 3_600_000).toISOString(),
        config,
      },
    }),
  );
  await page.route("**/api/public/v1/sessions/*/messages/stream", (route) =>
    route.fulfill({ status: 502, body: "bad gateway" }),
  );
  let counter = 0;
  await page.route("**/api/public/v1/sessions/*/messages", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: [] });
    }
    counter += 1;
    return route.fulfill({
      status: 201,
      json: {
        conversation_id: "c1",
        visitor_message: {
          id: `v-${counter}`,
          created_at: "2026-10-25T10:00:00Z",
        },
        ai_message: {
          id: `a-${counter}`,
          text: "Returns are accepted within 14 days.\n- Keep the receipt\n- Keep the packaging\n- Contact support to start a return",
          citations: [],
          can_answer: true,
          needs_human: false,
          created_at: "2026-10-25T10:00:01Z",
        },
        kind: "answer",
        language: lang,
      },
    });
  });
}

async function boxOf(frame: FrameLocator, testId: string) {
  const box = await frame.getByTestId(testId).boundingBox();
  expect(box, `${testId} is rendered`).not.toBeNull();
  return box!;
}

async function expectInsideFrame(page: Page, frame: FrameLocator) {
  const outer = await page.getByTestId("widget-frame").boundingBox();
  expect(outer).not.toBeNull();
  const viewport = page.viewportSize()!;
  expect(outer!.y).toBeGreaterThanOrEqual(0);
  expect(outer!.y + outer!.height).toBeLessThanOrEqual(viewport.height);
  expect(outer!.x).toBeGreaterThanOrEqual(0);
  expect(outer!.x + outer!.width).toBeLessThanOrEqual(viewport.width);
  for (const id of ["widget-input", "widget-send"]) {
    const box = await boxOf(frame, id);
    expect(box.y, `${id} top`).toBeGreaterThanOrEqual(outer!.y);
    expect(box.y + box.height, `${id} bottom`).toBeLessThanOrEqual(
      outer!.y + outer!.height + 0.5,
    );
  }
}

async function threadHeight(frame: FrameLocator) {
  const box = await frame.locator(".widget-thread").boundingBox();
  expect(box).not.toBeNull();
  return box!.height;
}

async function ask(frame: FrameLocator, text: string) {
  const replies = frame.locator(".widget-bubble:not(.visitor)");
  const before = await replies.count();
  await frame.getByTestId("widget-input").fill(text);
  await frame.getByTestId("widget-send").click();
  await expect(replies).toHaveCount(before + 1);
  await expect(frame.getByTestId("widget-input")).toBeEnabled();
}

for (const layout of LAYOUTS) {
  test(`widget panel layout holds up: ${layout.name}`, async ({ page }) => {
    await registerStaffSession(page, "widget-layout");
    await page.setViewportSize(layout.viewport);
    await mockWidget(page, layout.lang, layout.dir);
    await page.goto(`/widget/sample?locator=${LOCATOR}`);
    await page.getByTestId("widget-bubble").click();
    const frame = page.frameLocator("[data-testid=widget-frame]");
    await expect(frame.getByTestId("widget-title")).toHaveText("Layout bot");
    await expect(frame.getByTestId("widget-frame-body")).toHaveAttribute(
      "dir",
      layout.dir,
    );

    // Opened and empty: input row visible, a readable message area, lead form closed.
    await expectInsideFrame(page, frame);
    expect(await threadHeight(frame)).toBeGreaterThanOrEqual(200);
    await expect(frame.getByTestId("widget-lead-form")).toHaveCount(0);

    // Six exchanges scroll inside the panel; the panel itself does not grow.
    const panelBefore = await page.getByTestId("widget-frame").boundingBox();
    for (let index = 1; index <= 6; index += 1) {
      await ask(frame, `Question number ${index}`);
    }
    const panelAfter = await page.getByTestId("widget-frame").boundingBox();
    expect(panelAfter!.height).toBe(panelBefore!.height);
    const scroll = await frame.locator(".widget-thread").evaluate((node) => ({
      scrollHeight: node.scrollHeight,
      clientHeight: node.clientHeight,
      scrollTop: node.scrollTop,
    }));
    expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
    expect(scroll.scrollTop).toBeGreaterThan(0);
    await expectInsideFrame(page, frame);

    // The contact sheet slides over the panel and closes again without moving the thread.
    const closedHeight = await threadHeight(frame);
    await frame.getByTestId("widget-lead-open").click();
    await expect(frame.getByTestId("widget-lead-form")).toBeVisible();
    await expectInsideFrame(page, frame);
    expect(await threadHeight(frame)).toBeGreaterThanOrEqual(120);
    await frame.locator(".widget-sheet-close").click();
    await expect(frame.getByTestId("widget-lead-form")).toHaveCount(0);
    await expectInsideFrame(page, frame);
    expect(await threadHeight(frame)).toBeCloseTo(closedHeight, 0);
  });
}
