import { expect, test } from "@playwright/test";

// P2-00: the dashboard pages must send hardening headers on every response
// (verified against the real Next.js server started by the Playwright
// webServer). The same-origin API proxy is an external rewrite to the
// FastAPI process, so next.config headers do not attach to its responses —
// in production the gateway in front of web+api adds them (P2-00 report).
test("dashboard responses carry Referrer-Policy, nosniff and frame-ancestors 'none'", async ({
  request,
}) => {
  for (const path of ["/", "/login", "/register"]) {
    const response = await request.get(path);
    expect(response.ok()).toBeTruthy();
    expect(response.headers()["referrer-policy"]).toBe("no-referrer");
    expect(response.headers()["x-content-type-options"]).toBe("nosniff");
    expect(response.headers()["content-security-policy"]).toContain(
      "frame-ancestors 'none'",
    );
  }
});
