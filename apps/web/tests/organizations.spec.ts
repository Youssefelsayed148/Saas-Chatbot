import { expect, test } from "@playwright/test";
import { registerAdmin } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

test("staff create and manage an organization across its four tabs", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const email = `organizations.${Date.now()}@example.com`;
  await registerAdmin(page, "Org Staff", { email });
  promoteToStaff(email);
  await page.goto("/platform");
  await page.getByTestId("organization-name").fill(`New Org ${Date.now()}`);
  await page.getByTestId("organization-plan").selectOption("starter");
  await page.getByTestId("organization-submit").click();
  await page.waitForURL(/\/platform\/clients\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "New Org",
  );
  await page.getByRole("combobox", { name: "Plan" }).selectOption("pro");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Organization updated.")).toBeVisible();
  for (const label of ["Overview", "Members", "Bots", "Knowledge"] as const) {
    await page.getByRole("tab", { name: label }).click();
    await expect(page.getByRole("tabpanel", { name: label })).toBeVisible();
  }
  const orgId = page.url().split("/").at(-1)!;
  const csrf = await page.evaluate(
    () =>
      document.cookie
        .split("; ")
        .find((part) => part.startsWith("chatbot_csrf="))
        ?.split("=")[1] ?? "",
  );
  const createdBot = await page.request.post(
    `/api/v1/platform/tenants/${orgId}/bots`,
    { headers: { "X-CSRF-Token": csrf }, data: { name: "Knowledge Bot" } },
  );
  expect(createdBot.status()).toBe(201);
  await page.reload();
  await page.getByRole("tab", { name: "Knowledge" }).click();
  await page.getByRole("link", { name: "Open Knowledge" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/app/${orgId}/bots/[0-9a-f-]+/knowledge`),
  );
});

test("non-staff cannot reach /platform", async ({ page }) => {
  const email = `nonstaff-platform.${Date.now()}@example.com`;
  await registerAdmin(page, "Non Staff", { email });
  await page.goto("/platform");
  await expect(page).toHaveURL(/\/app(?:\/|$)/);
});
