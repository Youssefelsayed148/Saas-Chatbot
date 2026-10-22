import { expect, test, type Page } from "@playwright/test";
import { safetyFixture, botBase, botId, tenant } from "./group-c-fixtures";

/** Batch C bot settings: names, tone, theme, readiness, backfill (API mocked). */

const READINESS = {
  ready: false,
  items: [
    {
      id: "support_contact",
      label: "Support email or phone",
      status: "todo",
      detail: "Add a support email or phone so visitors know where to go.",
      section: "contact",
    },
    {
      id: "welcome_message",
      label: "Welcome message",
      status: "ok",
      detail: "Custom welcome message set.",
      section: "messages",
    },
    {
      id: "allowed_domains",
      label: "Allowed websites",
      status: "warning",
      detail: "Open: any website can embed this widget.",
      section: "access",
    },
    {
      id: "knowledge_published",
      label: "Knowledge published",
      status: "todo",
      detail: "Nothing is published yet.",
      section: "knowledge",
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

function ragStatus(embeddingReady: boolean) {
  return {
    tier: "standard",
    tier_targets: {
      standard: { provider: "openrouter", model: null },
      premium: { provider: "openai", model: "gpt-4.1-nano" },
    },
    retrieval_mode: "hybrid",
    active_embedding_model: null,
    embedding_ready: embeddingReady,
    limits: {},
    effective_limits: {},
    usage: {},
    backfill: null,
  };
}

async function openSettings(
  page: Page,
  options: {
    config?: Record<string, unknown>;
    tone?: string | null;
    embeddingReady?: boolean;
    patchStatus?: number;
    patchBody?: unknown;
  } = {},
) {
  await safetyFixture(page);
  const bot = {
    id: botId,
    name: "Safety bot",
    status: "active",
    config: options.config ?? {},
    tone_and_rules: options.tone ?? null,
    widget_locator: "fixture-locator",
  };
  const patches: Array<Record<string, unknown>> = [];
  // Routes registered later win over the shared fixture's catch-all.
  await page.route(`**/api/v1/tenants/${tenant}/bots/${botId}`, (route) => {
    if (route.request().method() === "PATCH") {
      patches.push(route.request().postDataJSON());
      if (options.patchStatus && options.patchStatus >= 400) {
        return route.fulfill({
          status: options.patchStatus,
          json: options.patchBody,
        });
      }
    }
    return route.fulfill({ json: bot });
  });
  await page.route(
    `**/api/v1/tenants/${tenant}/bots/${botId}/readiness`,
    (route) => route.fulfill({ json: READINESS }),
  );
  await page.route(`**/api/v1/tenants/${tenant}/bots/${botId}/rag`, (route) =>
    route.fulfill({ json: ragStatus(options.embeddingReady ?? false) }),
  );
  await page.goto(`${botBase}/settings`);
  await expect(page.getByLabel("Assistant name")).toBeVisible();
  return { patches };
}

const save = (page: Page) =>
  page.getByRole("button", { name: "Save settings", exact: true }).click();

test("one Assistant name field; business name defaults to the organization", async ({
  page,
}) => {
  const { patches } = await openSettings(page);
  await expect(page.getByLabel("Bot name")).toHaveCount(0);
  await expect(page.getByLabel("Assistant name")).toHaveValue("Safety bot");
  await expect(page.getByLabel("Business name")).toHaveValue("Safety org");
  await page.getByLabel("Assistant name").fill("Aida");
  await save(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({
    name: "Aida",
    config: { assistant_name: "Aida", business_name: "Safety org" },
  });
});

test("an existing assistant name wins over the legacy bot name", async ({
  page,
}) => {
  await openSettings(page, {
    config: { assistant_name: "Mib", business_name: "Mib Co" },
  });
  await expect(page.getByLabel("Assistant name")).toHaveValue("Mib");
  await expect(page.getByLabel("Business name")).toHaveValue("Mib Co");
});

test("staff tone and rules: textarea, counter, guidance, saved in the one request", async ({
  page,
}) => {
  const { patches } = await openSettings(page, { tone: "Be warm." });
  const tone = page.getByRole("textbox", { name: "Tone and rules" });
  await expect(tone).toHaveValue("Be warm.");
  await expect(page.getByTestId("tone-counter")).toContainText("8 / 2000");
  await expect(page.getByTestId("tone-and-rules-section")).toContainText(
    /cannot override the grounding, safety or answer format rules/,
  );
  await tone.fill("Warm and brief.");
  await expect(page.getByTestId("tone-counter")).toContainText("15 / 2000");
  await save(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({ tone_and_rules: "Warm and brief." });
});

test("theme preset drives the preview and is saved with the form", async ({
  page,
}) => {
  const { patches } = await openSettings(page);
  await page.getByRole("radio", { name: /Midnight glass/ }).check();
  const preview = page.getByTestId("widget-preview-frame");
  await expect(preview).toHaveAttribute("srcdoc", /--w-header:#1e1b4b/);
  await expect(preview).toHaveAttribute(
    "srcdoc",
    /data-widget-variant="glass"/,
  );
  const inner = page.frameLocator('[data-testid="widget-preview-frame"]');
  await expect(inner.locator(".widget-header")).toHaveCSS(
    "background-color",
    "rgb(30, 27, 75)",
  );
  await expect(inner.locator(".widget-bubble.visitor")).toHaveCSS(
    "background-color",
    "rgb(79, 70, 229)",
  );
  await expect(page.getByTestId("widget-preview-launcher")).toHaveCSS(
    "background-color",
    "rgb(79, 70, 229)",
  );
  await save(page);
  await expect.poll(() => patches.length).toBe(1);
  expect(patches[0]).toMatchObject({
    config: {
      theme: {
        preset: "midnight-glass",
        header: "#1e1b4b",
        send_button: "#818cf8",
        user_bubble: "#4f46e5",
        bot_bubble: "#1e293b",
        text: "#f1f5f9",
        launcher: "#4f46e5",
      },
    },
  });
});

test("an untouched bot sends no theme and the default preview keeps today's look", async ({
  page,
}) => {
  const { patches } = await openSettings(page);
  await expect(page.getByTestId("widget-preview-frame")).not.toHaveAttribute(
    "srcdoc",
    /--w-header:/,
  );
  await save(page);
  await expect.poll(() => patches.length).toBe(1);
  expect((patches[0].config as Record<string, unknown>).theme).toBeUndefined();
});

test("per-slot palette and picker; low contrast warns and can be fixed", async ({
  page,
}) => {
  await openSettings(page);
  await page.getByRole("radio", { name: /Ocean/ }).check();
  await expect(page.getByTestId("theme-contrast")).toContainText("passed");
  await page
    .getByRole("button", { name: "Header: #4f46e5", exact: true })
    .click();
  await expect(page.getByTestId("theme-value-header")).toHaveText("#4f46e5");
  await expect(page.getByTestId("theme-custom-note")).toBeVisible();
  await page.getByLabel("Assistant message text custom colour").fill("#eeeeee");
  await expect(page.getByTestId("theme-contrast")).toContainText("Warning");
  await page.getByTestId("theme-fix-contrast").click();
  await expect(page.getByTestId("theme-contrast")).toContainText("passed");
  await page.getByRole("button", { name: "Reset Header to default" }).click();
  await expect(page.getByTestId("theme-value-header")).toHaveText("default");
});

test("a 422 on the theme shows inline and saves nothing else", async ({
  page,
}) => {
  const { patches } = await openSettings(page, {
    patchStatus: 422,
    patchBody: {
      error: {
        code: "VALIDATION_ERROR",
        message: "Request body failed validation.",
        details: {
          fields: [
            {
              field: "config.theme.header",
              message: "Theme colours must be hex values like #1a2b3c.",
            },
          ],
        },
      },
    },
  });
  await page.getByRole("radio", { name: /Ocean/ }).check();
  await save(page);
  await expect(page.getByTestId("field-error-theme")).toContainText(
    "must be hex",
  );
  expect(patches).toHaveLength(1);
});

test("readiness checklist reflects the API state with links to the section", async ({
  page,
}) => {
  await openSettings(page);
  const card = page.getByTestId("bot-readiness");
  await expect(card).toBeVisible();
  await expect(page.getByTestId("readiness-summary")).toContainText(
    "still missing",
  );
  await expect(page.getByTestId("readiness-support_contact")).toHaveAttribute(
    "data-status",
    "todo",
  );
  await expect(page.getByTestId("readiness-welcome_message")).toHaveAttribute(
    "data-status",
    "ok",
  );
  await expect(page.getByTestId("readiness-allowed_domains")).toHaveAttribute(
    "data-status",
    "warning",
  );
  await expect(
    page.getByTestId("readiness-support_contact").getByRole("link", {
      name: "Fix",
    }),
  ).toHaveAttribute("href", "#field-support_email");
  await expect(
    page.getByTestId("readiness-knowledge_published").getByRole("link", {
      name: "Fix",
    }),
  ).toHaveAttribute("href", /\/knowledge$/);
  await expect(
    page.getByTestId("readiness-welcome_message").getByRole("link"),
  ).toHaveCount(0);
});

test("backfill action is hidden when embeddings are up to date", async ({
  page,
}) => {
  await openSettings(page, { embeddingReady: true });
  await expect(page.getByTestId("rag-tier-control")).toBeVisible();
  await expect(page.getByTestId("rag-backfill-action")).toHaveCount(0);
  await expect(page.getByTestId("rag-backfill-uptodate")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start embedding backfill" }),
  ).toHaveCount(0);
});

test("backfill action shows in normal style when needed and keeps its confirmation", async ({
  page,
}) => {
  await openSettings(page, { embeddingReady: false });
  const trigger = page.getByRole("button", {
    name: "Start embedding backfill",
    exact: true,
  });
  await expect(trigger).toBeVisible();
  // Not the red danger look: it takes the regular button background.
  const [triggerBg, normalBg] = await Promise.all([
    trigger.evaluate((el) => getComputedStyle(el).backgroundColor),
    page
      .getByRole("button", { name: "Save settings", exact: true })
      .evaluate((el) => getComputedStyle(el).backgroundColor),
  ]);
  expect(triggerBg).toBe(normalBg);
  await trigger.click();
  await expect(
    page.getByRole("dialog", { name: "Start embedding backfill?" }),
  ).toBeVisible();
});

function frameConfig(extra: Record<string, unknown>) {
  return {
    available: true,
    config: {
      bot_name: "Theme check",
      assistant_name: "Assistant",
      welcome_message: { en: "Hello there", ar: "Hello there" },
      opening_questions: [],
      colour: "#123456",
      position: "right",
      default_language: "en",
      dir: "ltr",
      ...extra,
    },
  };
}

async function captureBrand(page: Page) {
  // Loaded top-level, the frame posts to itself; the real loader reads this
  // message to colour the launcher button on the host page.
  await page.addInitScript(() => {
    const seen: unknown[] = [];
    (window as unknown as { __brand: unknown[] }).__brand = seen;
    window.addEventListener("message", (event) => {
      if ((event.data as { type?: string })?.type === "chatbot:brand")
        seen.push(event.data);
    });
  });
}

test("widget frame applies the saved theme through CSS variables", async ({
  page,
}) => {
  await captureBrand(page);
  await page.route("**/api/public/v1/widgets/themed/config", (route) =>
    route.fulfill({
      json: frameConfig({
        theme: {
          preset: "ocean",
          header: "#0b5ea8",
          send_button: "#0b5ea8",
          user_bubble: "#0b5ea8",
          bot_bubble: "#eaf3fb",
          text: "#0f2a43",
          launcher: "#c2410c",
        },
      }),
    }),
  );
  await page.goto("/widget/frame?locator=themed");
  await expect(page.getByTestId("widget-title")).toHaveText("Theme check");
  await expect(page.locator(".widget-header")).toHaveCSS(
    "background-color",
    "rgb(11, 94, 168)",
  );
  const bubble = page.getByTestId("widget-ai-msg").first();
  await expect(bubble).toHaveCSS("background-color", "rgb(234, 243, 251)");
  await expect(bubble).toHaveCSS("color", "rgb(15, 42, 67)");
  await expect(page.getByTestId("widget-send")).toHaveCSS(
    "background-color",
    "rgb(11, 94, 168)",
  );
  const brand = await page.evaluate(
    () => (window as unknown as { __brand: Array<{ colour: string }> }).__brand,
  );
  expect(brand.at(-1)?.colour).toBe("#c2410c");
});

test("widget frame without a theme keeps today's look", async ({ page }) => {
  await captureBrand(page);
  await page.route("**/api/public/v1/widgets/plain/config", (route) =>
    route.fulfill({ json: frameConfig({}) }),
  );
  await page.goto("/widget/frame?locator=plain");
  await expect(page.getByTestId("widget-title")).toHaveText("Theme check");
  await expect(page.locator(".widget-header")).toHaveCSS(
    "background-color",
    "rgb(18, 52, 86)",
  );
  await expect(page.getByTestId("widget-send")).toHaveCSS(
    "background-color",
    "rgb(18, 52, 86)",
  );
  const brand = await page.evaluate(
    () => (window as unknown as { __brand: Array<{ colour: string }> }).__brand,
  );
  expect(brand.at(-1)?.colour).toBe("#123456");
});
