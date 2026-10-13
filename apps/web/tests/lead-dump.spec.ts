import { test } from "@playwright/test";

test("debug lead form", async ({ page }) => {
  await page.goto(
    "/widget/sample?locator=dump0000&site=store-a",
  );
  await page.waitForTimeout(1500);
  await page.getByTestId("widget-bubble").click();
  await page.waitForTimeout(1200);
  const frame = page
    .frameLocator("[data-testid='widget-frame']")
    .locator("[data-testid='widget-frame-body']");
  frame.on("response", (r) => console.log("FRAME", r.status(), r.url()));
  await page.waitForTimeout(300);
  await frame.getByTestId("widget-lead-open").click();
  await frame.getByTestId("widget-lead-name").fill("Testy");
  await frame.getByTestId("widget-lead-email").fill("testy@example.com");
  await frame.getByTestId("widget-lead-consent").check();
  await frame.getByTestId("widget-lead-submit").click();
  await page.waitForTimeout(1200);
  const done = await frame.getByTestId("widget-lead-done").count();
  const err = await frame.getByTestId("widget-lead-error").count();
  console.log("DONE:", done, "ERR:", err ?? "(none)");
});
