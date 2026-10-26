import { expect, test } from "@playwright/test";
import {
  registerAdmin,
  registerAndPrepareBot,
  registerOperator,
} from "./e2e-helpers";

test("staff creates bots from the directory and locked organization form", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { tenantId } = await registerOperator(page, "staff-bots");
  // The signup fixture already has one bot; raise capacity through the existing staff contract.
  const headers = {
    "X-CSRF-Token": (await page.context().cookies()).find(
      (c) => c.name === "chatbot_csrf",
    )!.value,
  };
  expect(
    (
      await page.request.patch(
        `/api/v1/platform/tenants/${tenantId}/quota-overrides`,
        {
          headers,
          data: {
            reason: "Browser fixture bot capacity",
            limits: { bots: 4 },
          },
        },
      )
    ).status(),
  ).toBe(200);
  await page.goto("/platform/bots");
  const form = page.getByRole("region", { name: "Create bot", exact: true });
  await form
    .getByRole("combobox", { name: "Organization" })
    .selectOption(tenantId);
  const name = `Directory bot ${Date.now()}`;
  await form.getByLabel("Bot name", { exact: true }).fill(name);
  await form.getByRole("button", { name: "Create bot", exact: true }).click();
  await expect(form.getByRole("status")).toContainText("Bot created");
  const row = page.getByRole("row").filter({ hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge$/);
  await page.goto("/platform/bots");
  await page
    .getByRole("row")
    .filter({ hasText: name })
    .getByRole("link", { name: "Settings", exact: true })
    .click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByText(/Organization:.*read-only/)).toBeVisible();
  await page.goto(`/platform/clients/${tenantId}`);
  await page.getByRole("tab", { name: "Bots", exact: true }).click();
  const locked = page.getByRole("region", { name: "Create bot", exact: true });
  await expect(locked.getByRole("combobox")).toHaveCount(0);
  await expect(locked).toContainText("(fixed)");
  await locked.getByLabel("Bot name").fill(`Organization bot ${Date.now()}`);
  await locked.getByRole("button", { name: "Create bot", exact: true }).click();
  await expect(locked.getByRole("status")).toContainText("Bot created");
  await locked.getByRole("link", { name: "Knowledge", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge$/);
  await page.goto("/platform");
  await expect(page.getByTestId("onboarding-form")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Onboard a new client" }),
  ).toHaveCount(0);
});

test("authenticated non-staff cannot reach the Bots section", async ({
  page,
}) => {
  await registerAdmin(page, "non-staff-bots");
  await page.goto("/platform/bots");
  await expect(page).not.toHaveURL(/\/platform\/bots$/);
  await expect(
    page.getByRole("region", { name: "Create bot", exact: true }),
  ).toHaveCount(0);
});

test("settings normalizes allowed domains and shows inline field errors", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const { tenantId, botId } = await registerAndPrepareBot(page, "domains");
  await page.goto(`/app/${tenantId}/bots/${botId}/settings`);
  const domains = page.getByLabel(/Allowed domains/);
  await domains.fill("not a domain");
  await page.getByRole("button", { name: "Save settings" }).click();
  const inline = page.getByTestId("field-error-allowed_domains");
  await expect(inline).toBeVisible();
  await expect(inline).toContainText("hostnames");
  // The submitted value itself is never echoed back.
  await expect(inline).not.toContainText("not a domain");
  // Normalization: scheme, port, path, case and trailing dot reduce to
  // bare hostnames; localhost stays accepted in the non-production harness.
  await domains.fill("HTTP://Example.COM/\nhttp://localhost:5500/");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  await expect(domains).toHaveValue("example.com\nlocalhost");
});
