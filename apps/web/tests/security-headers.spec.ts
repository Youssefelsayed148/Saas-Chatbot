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

// P4-02: the widget frame must be frameable by client sites (scoped
// frame-ancestors), while the dashboard stays unframeable. Next.js applies
// every matching next.config rule; the LAST value of a header key wins, so
// the /widget rule is declared AFTER the dashboard rule in next.config.
test("widget frame page relaxes frame-ancestors only under /widget", async ({
  request,
}) => {
  const frameResponse = await request.get("/widget/frame", { maxRedirects: 0 });
  expect(frameResponse.ok()).toBeTruthy();
  expect(frameResponse.headers()["content-security-policy"]).toBe(
    "frame-ancestors http: https:",
  );
  const loaderResponse = await request.get("/widget/v1/loader.js");
  expect(loaderResponse.ok()).toBeTruthy();
  expect(loaderResponse.headers()["content-type"]).toContain("javascript");
});
