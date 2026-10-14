import { expect, test } from "@playwright/test";

const PASSWORD = "Str0ngPass!";
const uniqueEmail = () =>
  `crm.${Date.now()}.${Math.floor(Math.random() * 1_000_000)}@example.com`;

test("owner creates, edits, and reviews a contact profile", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("/app");
  await page.getByLabel("Name").fill(`CRM Org ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/app\/[0-9a-f-]{36}\/bots$/);

  const tenantId = new URL(page.url()).pathname.split("/")[2];
  await page.goto(`/app/${tenantId}/contacts`);
  await expect(page.getByRole("heading", { name: "Contacts" })).toBeVisible();
  await page.getByLabel("Name", { exact: true }).fill("Ada Lovelace");
  await page.getByLabel("Email", { exact: true }).fill("ada.crm@example.com");
  await page.getByRole("button", { name: "Create contact" }).click();
  await page.getByRole("link", { name: "Ada Lovelace" }).click();
  await expect(
    page.getByRole("heading", { name: "Ada Lovelace" }),
  ).toBeVisible();
  await page.getByLabel("Tags (comma separated)").fill("vip, website");
  await page
    .getByLabel("Custom fields (JSON, up to 20 keys)")
    .fill('{"source":"playwright"}');
  await page.getByRole("button", { name: "Save contact" }).click();
  await expect(page.getByText("No conversations or notes.")).toBeVisible();
  await page.goto(`/app/${tenantId}/contacts`);
  await expect(
    page.getByRole("row", { name: /Ada Lovelace.*ada\.crm@example\.com/ }),
  ).toBeVisible();
});
