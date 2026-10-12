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
        // Dashboard-wide hardening (P2-00). frame-ancestors 'none': the dashboard
        // must never be framed. The P4 widget frame page will need its own
        // scoped header set; that page does not exist yet.
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
