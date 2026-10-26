import { expect, test, type Page } from "@playwright/test";
import { safetyFixture, botBase, botId, tenant } from "./group-c-fixtures";

/** UI polish B6: bot settings page (API mocked, no database needed). */

const READINESS = {
  ready: false,
  items: [
    {
      id: "welcome_message",
      label: "Welcome message",
      status: "ok",
      detail: "Custom welcome message set.",
      section: "messages",
    },
    {
      id: "support_contact",
      label: "Support email or phone",
      status: "todo",
      detail: "Add a support email or phone so visitors know where to go.",
      section: "contact",
    },
    {
      id: "model_reachable",
      label: "Model reachable",
      status: "warning",
      detail: "The last 2 model call(s) all failed.",
      section: "tier",
    },
    {
      id: "tier",
      label: "AI tier",
      status: "ok",
      detail: "Standard tier selected.",
      section: "tier",
    },
  ],
};

async function openSettings(page: Page) {
  await safetyFixture(page);
  const bot = {
    id: botId,
    name: "Safety bot",
    status: "active",
    config: {},
    tone_and_rules: null,
    widget_locator: "fixture-locator",
  };
  const patches: Array<Record<string, unknown>> = [];
  const tierPatches: Array<Record<string, unknown>> = [];
  await page.route(`**/api/v1/tenants/${tenant}/bots/${botId}`, (route) => {
    if (route.request().method() === "PATCH")
      patches.push(route.request().postDataJSON());
    return route.fulfill({ json: bot });
  });
  await page.route(
    `**/api/v1/tenants/${tenant}/bots/${botId}/readiness`,
    (route) => route.fulfill({ json: READINESS }),
  );
  await page.route(`**/api/v1/tenants/${tenant}/bots/${botId}/rag`, (route) => {
    if (route.request().method() === "PATCH")
      tierPatches.push(route.request().postDataJSON());
    return route.fulfill({
      json: {
        tier: "standard",
        tier_targets: {
          standard: { provider: "openrouter", model: null },
          premium: { provider: "openai", model: "gpt-5.4-nano" },
        },
        retrieval_mode: "hybrid",
        active_embedding_model: null,
        embedding_ready: true,
        limits: {},
        effective_limits: {},
        usage: {},
        backfill: null,
      },
    });
  });
  await page.goto(`${botBase}/settings`);
  await expect(page.getByLabel("Assistant name")).toBeVisible();
  return { patches, tierPatches };
}

const saveButton = (page: Page) =>
  page.getByRole("button", { name: "Save settings", exact: true });

test("editing shows the sticky save bar; Save settings persists and clears it", async ({
  page,
}) => {
  const { patches } = await openSettings(page);
  const bar = page.getByRole("region", { name: "Unsaved changes" });
  // Clean: no unsaved-changes bar, but one Save settings button is present.
  await expect(bar).toHaveCount(0);
  await expect(saveButton(page)).toHaveCount(1);
  await page.getByLabel("Assistant name").fill("Aida");
  await expect(bar).toBeVisible();
  // Never two buttons with the same name at once.
  await expect(saveButton(page)).toHaveCount(1);
  await expect(
    bar.getByRole("button", { name: "Save settings" }),
  ).toBeVisible();
  await saveButton(page).click();
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({ name: "Aida" });
  await expect(page.getByText("Settings saved.")).toBeVisible();
  await expect(bar).toHaveCount(0);
  await expect(saveButton(page)).toHaveCount(1);
});

test("section nav lists the six sections and jumps to them", async ({
  page,
}) => {
  await openSettings(page);
  const nav = page.getByRole("navigation", { name: "Settings sections" });
  for (const label of [
    "Identity",
    "Appearance",
    "Messages",
    "Handoff",
    "Access",
    "AI",
  ]) {
    await expect(
      nav.getByRole("link", { name: label, exact: true }),
    ).toBeVisible();
  }
  await nav.getByRole("link", { name: "Access", exact: true }).click();
  await expect(page).toHaveURL(/#access$/);
  await expect(page.locator("#access")).toBeInViewport();
  await expect(
    nav.getByRole("link", { name: "Access", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  await expect(
    nav.getByRole("link", { name: "Identity", exact: true }),
  ).not.toHaveAttribute("aria-current", /.+/);
});

test("Human handoff is a switch that toggles and saves", async ({ page }) => {
  const { patches } = await openSettings(page);
  const handoff = page.getByRole("switch", { name: /Human handoff enabled/ });
  await expect(handoff).toBeChecked();
  await handoff.click();
  await expect(handoff).not.toBeChecked();
  await expect(
    page.getByRole("region", { name: "Unsaved changes" }),
  ).toBeVisible();
  await saveButton(page).click();
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({ config: { handoff_enabled: false } });
});

test("widget colour shows a contrast result and flags a bad hex", async ({
  page,
}) => {
  await openSettings(page);
  const colour = page.getByLabel("Widget colour (hex, e.g. #1a2b3c)");
  const message = page.getByTestId("brand-colour-message");
  await colour.fill("#123456");
  await expect(message).toContainText("Contrast");
  await expect(message).toContainText("Passes");
  await colour.fill("#12");
  await expect(message).toHaveText("Enter a colour as #rrggbb.");
  await expect(colour).toHaveAttribute("aria-invalid", "true");
  await colour.fill("");
  await expect(message).toContainText("Optional");
});

test("the AI tier saves immediately with inline feedback inside the AI section", async ({
  page,
}) => {
  const { tierPatches } = await openSettings(page);
  const ai = page.locator("#ai");
  const tier = ai.getByTestId("rag-tier-control");
  await expect(tier).toBeVisible();
  await expect(tier).toContainText("Saves immediately");
  await tier.getByLabel("Tier").selectOption("premium");
  await expect(tier.getByText("AI tier saved.")).toBeVisible();
  expect(tierPatches).toEqual([{ tier: "premium" }]);
});

test("staff see a collapsible Diagnostics block with retrieval details", async ({
  page,
}) => {
  await openSettings(page);
  const ai = page.locator("#ai");
  const mode = ai.getByTestId("rag-retrieval-mode");
  await expect(mode).toHaveText("hybrid");
  await expect(mode).toBeHidden();
  await ai.getByText("Diagnostics", { exact: true }).click();
  await expect(mode).toBeVisible();
  await expect(ai.getByTestId("rag-embedding-model")).toHaveText("none");
  await expect(ai.getByTestId("rag-backfill-status")).toHaveText("never run");
});

test("readiness shows progress, failing items first and the model banner", async ({
  page,
}) => {
  await openSettings(page);
  const card = page.getByTestId("bot-readiness");
  await expect(page.getByTestId("readiness-count")).toHaveText("2/4 ready");
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "2",
  );
  const banner = card.getByTestId("readiness-model_reachable");
  await expect(banner).toContainText("The last 2 model call(s) all failed.");
  await expect(banner.getByRole("link", { name: "Fix" })).toHaveAttribute(
    "href",
    "#settings-ai-tier",
  );
  const rows = card.locator(".readiness-list > li");
  await expect(rows.first()).toHaveAttribute("data-status", "todo");
  await expect(rows.last()).toHaveAttribute("data-status", "ok");
  // Status labels are not controls.
  await expect(card.getByRole("button")).toHaveCount(0);
});

test("settings fit a phone width without horizontal page scroll", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await openSettings(page);
  await page.getByLabel("Assistant name").fill("Aida");
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
