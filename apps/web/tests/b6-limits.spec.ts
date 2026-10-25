import { expect, test, type Page } from "@playwright/test";

const tenantId = "11111111-1111-4111-8111-111111111111";
const botId = "33333333-3333-4333-8333-333333333333";

type Limits = Record<string, number | null>;

// Staff session plus a fully mocked API: no database is needed for this spec.
async function mockPanel(page: Page) {
  let limits: Limits = {};
  const patches: unknown[] = [];
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "operator-fixture",
        email: "fixture@example.com",
        is_platform_staff: true,
        memberships: [],
      },
    }),
  );
  await page.route("**/api/v1/auth/config", (route) =>
    route.fulfill({ json: { self_serve_signup: false } }),
  );
  await page.route("**/api/v1/platform/tenants?*", (route) =>
    route.fulfill({ json: { tenants: [], total: 0 } }),
  );
  await page.route(`**/api/v1/tenants/${tenantId}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith(`/bots/${botId}/rag/costs`))
      return route.fulfill({
        json: {
          costs: [
            {
              channel: "website",
              model: "unreported-model",
              event_type: "answer",
              events: 3,
              measured_tokens: 0,
              reserved_or_accounted_tokens: 900,
              cost_usd: "0",
              unmeasured_events: 3,
            },
            {
              channel: "website",
              model: "measured-model",
              event_type: "embedding",
              events: 2,
              measured_tokens: 1500,
              reserved_or_accounted_tokens: 1500,
              cost_usd: "0.42",
              unmeasured_events: 0,
            },
          ],
        },
      });
    if (path.endsWith(`/bots/${botId}/rag`)) {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON() as { limits: Limits | null };
        patches.push(body.limits);
        limits = body.limits ?? {};
        return route.fulfill({ status: 204, body: "" });
      }
      return route.fulfill({
        json: {
          limits,
          effective_limits: { ...{ monthly_tokens: 50000 }, ...limits },
          usage: { monthly_tokens: 1200 },
        },
      });
    }
    if (path.endsWith("/bots"))
      return route.fulfill({
        json: [
          {
            id: botId,
            tenant_id: tenantId,
            name: "Fixture bot",
            status: "active",
            config: {},
          },
        ],
      });
    if (path.endsWith("/analytics"))
      return route.fulfill({
        json: {
          total_conversations: 0,
          handoff_count: 0,
          handoff_rate: null,
          average_first_human_reply_seconds: null,
          conversations_by_channel: {},
          resolved_vs_open: { resolved: 0, open: 0 },
          sentiment_distribution: {},
          agent_workload: {},
        },
      });
    return route.fulfill({ json: [] });
  });
  return { patches };
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

test("editing a limit shows the sticky bar; saving clears it", async ({
  page,
}) => {
  const { patches } = await mockPanel(page);
  await page.goto(`/app/${tenantId}/analytics`);
  const panel = page.getByTestId("rag-operator-panel");
  await expect(panel).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Save AI limits", exact: true }),
  ).toHaveCount(0);
  const tokens = panel.getByRole("spinbutton", {
    name: "AI tokens per month",
    exact: true,
  });
  await expect(tokens).toHaveValue("");
  await expect(panel.getByText(/Effective limit: 50,000 tokens/)).toBeVisible();
  await tokens.fill("12345");
  await expect(
    panel.getByRole("region", { name: "Unsaved changes" }),
  ).toBeVisible();
  await panel.getByRole("button", { name: "Discard changes" }).click();
  await expect(tokens).toHaveValue("");
  await expect(
    panel.getByRole("button", { name: "Save AI limits", exact: true }),
  ).toHaveCount(0);
  await tokens.fill("12345");
  await panel
    .getByRole("button", { name: "Save AI limits", exact: true })
    .click();
  await expect(panel.getByText("AI limits saved.")).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Save AI limits", exact: true }),
  ).toHaveCount(0);
  await expect(tokens).toHaveValue("12345");
  expect((patches[0] as Limits).monthly_tokens).toBe(12345);
});

test("reset to plan defaults confirms, then saves", async ({ page }) => {
  const { patches } = await mockPanel(page);
  await page.goto(`/app/${tenantId}/analytics`);
  const panel = page.getByTestId("rag-operator-panel");
  const tokens = panel.getByRole("spinbutton", {
    name: "AI tokens per month",
    exact: true,
  });
  await tokens.fill("777");
  await panel
    .getByRole("button", { name: "Save AI limits", exact: true })
    .click();
  await expect(tokens).toHaveValue("777");
  await panel.getByRole("button", { name: "Reset to plan defaults" }).click();
  await page
    .getByRole("dialog", { name: "Reset to plan defaults?" })
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(panel.getByText("AI limits saved.")).toBeVisible();
  await expect(tokens).toHaveValue("");
  expect(patches.at(-1)).toBeNull();
});

test("unreported cost is never shown as a measured $0", async ({ page }) => {
  await mockPanel(page);
  await page.goto(`/app/${tenantId}/analytics`);
  const table = page.getByRole("table", { name: "AI cost breakdown" });
  const unreported = table
    .getByRole("row")
    .filter({ hasText: "unreported-model" });
  await expect(unreported).toContainText("Not reported");
  await expect(unreported).toContainText("3 events cost unreported");
  await expect(unreported).not.toContainText("$0");
  const measured = table.getByRole("row").filter({ hasText: "measured-model" });
  await expect(measured).toContainText("$0.42");
  await expect(measured).not.toContainText("cost unreported");
});
