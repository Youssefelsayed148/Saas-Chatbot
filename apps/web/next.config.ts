import type { NextConfig } from "next";

// The dashboard talks to the FastAPI backend through a same-origin proxy so the
// session cookies stay first-party (no CORS, no third-party cookie issues).
// The proxy target is configurable; container deployments point it at the api service.
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  poweredByHeader: false,
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  experimental: {
    // The same-origin proxy buffers request bodies when a proxy.ts exists.
    // 20 files × 10 MB (the upload batch cap, docs/14 §3) plus overhead; the
    // API still enforces its own per-file streaming limit (P2-02).
    proxyClientMaxBodySize: "220mb",
  },
  async headers() {
    return [
      {
        // Widget embed pages (P4-02): the frame MUST be frameable by client
        // sites, so this scoped rule loosens frame-ancestors only here while
        // the dashboard-wide rule below keeps frame-ancestors 'none'.
        // Next.js applies EVERY matching rule pair, and the LAST value of a
        // given header key wins — the widget rules come after the global ones.
        source: "/widget/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          {
            // Any http(s) customer site may frame the widget; the API surface
            // inside is the public widget contract (capability tokens + rate
            // limits), never the dashboard.
            key: "Content-Security-Policy",
            value: "frame-ancestors http: https:",
          },
        ],
      },
      {
        // Dashboard-wide hardening (P2-00). frame-ancestors 'none': the dashboard
        // must never be framed.
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
    ];
  },
};

export default config;
