import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type FrameLocator, type Page, test } from "@playwright/test";

/**
 * UI polish B1 (W-1..W-3): the open widget panel must be bounded AND readable
 * with the REAL loader.js and the REAL /widget/frame. Only the public API edge
 * is mocked. The loader is exercised from both copies (the source of truth in
 * packages/widget and the served one in apps/web/public) because
 * sync-loader.mjs copies the first over the second: a stale source silently
 * re-introduces a ~200px panel (the frame reports its own height back, the
 * first small value sticks).
 */

const LOCATOR = "panel";
const WEB_DIR = process.cwd();
const LOADERS = {
  source: path.resolve(WEB_DIR, "../../packages/widget/src/loader.js"),
  served: path.resolve(WEB_DIR, "public/widget/v1/loader.js"),
} as const;

const LAYOUTS = [
  { name: "1920x1140", viewport: { width: 1920, height: 1140 }, lang: "en", dir: "ltr" },
  { name: "1280x800", viewport: { width: 1280, height: 800 }, lang: "en", dir: "ltr" },
  { name: "375x667", viewport: { width: 375, height: 667 }, lang: "en", dir: "ltr" },
  { name: "RTL 1280x800", viewport: { width: 1280, height: 800 }, lang: "ar", dir: "rtl" },
] as const;

async function mockPublicApi(page: Page, lang: string, dir: string) {
  const config = {
    bot_name: "Panel bot",
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
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    counter += 1;
    return route.fulfill({
      status: 201,
      json: {
        conversation_id: "c1",
        visitor_message: { id: `v-${counter}`, created_at: "2026-10-25T10:00:00Z" },
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

/** A stand-in customer page on the app origin (no login needed). */
async function openHostPage(page: Page, loader: keyof typeof LOADERS) {
  await page.route("**/__panel-host.html", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><h1>Host page</h1><script src="/widget/v1/loader.js" data-locator="${LOCATOR}"></script></body></html>`,
    }),
  );
  if (loader === "source") {
    // Serve the packages/widget copy instead of the public one.
    await page.route("**/widget/v1/loader.js", (route) =>
      route.fulfill({
        contentType: "application/javascript",
        body: readFileSync(LOADERS.source, "utf8"),
      }),
    );
  }
  await page.goto("/__panel-host.html");
}

async function ask(frame: FrameLocator, text: string) {
  const replies = frame.locator(".widget-bubble:not(.visitor)");
  const before = await replies.count();
  await frame.getByTestId("widget-input").fill(text);
  await frame.getByTestId("widget-send").click();
  await expect(replies).toHaveCount(before + 1);
  await expect(frame.getByTestId("widget-input")).toBeEnabled();
}

async function expectReadablePanel(page: Page, frame: FrameLocator, minThread: number) {
  const viewport = page.viewportSize()!;
  const outer = (await page.getByTestId("widget-frame").boundingBox())!;
  // Bounded: inside the viewport, at most 640px, at least a readable minimum.
  expect(outer.y).toBeGreaterThanOrEqual(0);
  expect(outer.y + outer.height).toBeLessThanOrEqual(viewport.height);
  expect(outer.x).toBeGreaterThanOrEqual(0);
  expect(outer.x + outer.width).toBeLessThanOrEqual(viewport.width);
  expect(outer.height).toBeLessThanOrEqual(640.5);
  expect(outer.height).toBeGreaterThanOrEqual(Math.min(480, viewport.height * 0.6));
  // Thread is readable.
  const thread = (await frame.locator(".widget-thread").boundingBox())!;
  expect(thread.height).toBeGreaterThanOrEqual(minThread);
  // Composer fully inside the panel (and so inside the viewport).
  for (const id of ["widget-input", "widget-send"]) {
    const box = (await frame.getByTestId(id).boundingBox())!;
    expect(box.y, `${id} top`).toBeGreaterThanOrEqual(outer.y);
    expect(box.y + box.height, `${id} bottom`).toBeLessThanOrEqual(outer.y + outer.height + 0.5);
  }
}

for (const loader of ["source", "served"] as const) {
  for (const layout of LAYOUTS) {
    test(`widget panel is bounded and readable (${loader} loader, ${layout.name})`, async ({ page }) => {
      await page.setViewportSize(layout.viewport);
      await mockPublicApi(page, layout.lang, layout.dir);
      await openHostPage(page, loader);
      await page.getByTestId("widget-bubble").click();
      const frame = page.frameLocator("[data-testid=widget-frame]");
      await expect(frame.getByTestId("widget-title")).toHaveText("Panel bot");
      await expect(frame.getByTestId("widget-frame-body")).toHaveAttribute("dir", layout.dir);

      for (let index = 1; index <= 6; index += 1) {
        await ask(frame, `Question number ${index}`);
      }
      // Let any size feedback settle: the height must be stable and bounded.
      await page.waitForTimeout(400);
      await expect(frame.getByTestId("widget-lead-form")).toHaveCount(0);
      await expectReadablePanel(page, frame, 200);

      const closed = (await page.getByTestId("widget-frame").boundingBox())!.height;
      await frame.getByTestId("widget-lead-open").click();
      await expect(frame.getByTestId("widget-lead-form")).toBeVisible();
      await page.waitForTimeout(400);
      await expectReadablePanel(page, frame, 150);
      expect((await page.getByTestId("widget-frame").boundingBox())!.height).toBe(closed);

      // The thread scrollbar is the thin, token-coloured one (no arrow buttons).
      const scrollbar = await frame
        .locator(".widget-thread")
        .evaluate((node) => getComputedStyle(node).scrollbarWidth);
      expect(scrollbar).toBe("thin");
    });
  }
}

test("the served loader.js is the source loader.js (sync-loader keeps them identical)", () => {
  expect(readFileSync(LOADERS.served, "utf8")).toBe(readFileSync(LOADERS.source, "utf8"));
});
