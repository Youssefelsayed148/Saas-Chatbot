import { expect, test } from "@playwright/test";
import { registerOwner } from "./e2e-helpers";

test("owner creates, edits, and reviews a contact profile", async ({
  page,
}) => {
  const { tenantId } = await registerOwner(page, "CRM");
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
