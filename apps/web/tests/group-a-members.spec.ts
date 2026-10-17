import { expect, test } from "@playwright/test";
import { registerAdmin, uniqueEmail } from "./e2e-helpers";
import { promoteToStaff } from "./staff-helpers";

test("revoked members are absent from client Team and platform detail; pending invites remain", async ({
  page,
  browser,
}) => {
  const { tenantId } = await registerAdmin(page, "Group A members");
  const headers = {
    "X-CSRF-Token": (await page.context().cookies()).find(
      (c) => c.name === "chatbot_csrf",
    )!.value,
  };
  const revokedEmail = uniqueEmail("revoked-fixture");
  const invitation = await page.request.post(
    `/api/v1/tenants/${tenantId}/invitations`,
    {
      headers,
      data: { email: revokedEmail, role: "viewer" },
    },
  );
  expect(invitation.status()).toBe(201);
  const token = new URL(
    (await invitation.json()).link_path,
    "http://localhost",
  ).searchParams.get("token")!;
  const memberContext = await browser.newContext();
  const staffContext = await browser.newContext();
  try {
    const member = await memberContext.newPage();
    const registration = await member.request.post("/api/v1/auth/register", {
      data: {
        email: revokedEmail,
        password: "Str0ngPass!",
        invite_token: token,
      },
    });
    expect(registration.status()).toBe(201);
    const userId = (await registration.json()).id;
    const memberHeaders = {
      "X-CSRF-Token": (await memberContext.cookies()).find(
        (c) => c.name === "chatbot_csrf",
      )!.value,
    };
    expect(
      (
        await member.request.post("/api/v1/invitations/accept", {
          headers: memberHeaders,
          data: { token },
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await page.request.delete(
          `/api/v1/tenants/${tenantId}/members/${userId}`,
          { headers },
        )
      ).status(),
    ).toBe(204);
    const pendingEmail = uniqueEmail("pending-fixture");
    expect(
      (
        await page.request.post(`/api/v1/tenants/${tenantId}/invitations`, {
          headers,
          data: { email: pendingEmail, role: "viewer" },
        })
      ).status(),
    ).toBe(201);
    await page.goto(`/app/${tenantId}/settings/members`);
    await expect(
      page.getByRole("heading", { name: "Team", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(pendingEmail, { exact: true })).toBeVisible();
    await expect(page.getByText(revokedEmail, { exact: true })).toHaveCount(0);

    const staff = await staffContext.newPage();
    const staffEmail = uniqueEmail("operator-fixture");
    expect(
      (
        await staff.request.post("/api/v1/auth/register", {
          data: { email: staffEmail, password: "Str0ngPass!" },
        })
      ).status(),
    ).toBe(201);
    promoteToStaff(staffEmail);
    await staff.goto(`/platform/clients/${tenantId}`);
    await expect(staff.getByTestId("client-detail-name")).toContainText(
      "Group A members",
    );
    await expect(
      staff.getByRole("region", { name: "Pending invitations", exact: true }),
    ).toContainText(pendingEmail);
    await expect(staff.getByTestId("client-detail-members")).not.toContainText(
      revokedEmail,
    );
    expect(
      (
        await member.request.post("/api/v1/auth/login", {
          data: { email: revokedEmail, password: "Str0ngPass!" },
        })
      ).status(),
    ).toBe(401);
  } finally {
    await memberContext.close();
    await staffContext.close();
  }
});
