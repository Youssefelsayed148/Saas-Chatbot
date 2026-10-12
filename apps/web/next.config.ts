import type { NextConfig } from "next";

// The dashboard talks to the FastAPI backend through a same-origin proxy so the
// session cookies stay first-party (no CORS, no third-party cookie issues).
// The proxy target is configurable; container deployments point it at the api service.
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  poweredByHeader: false,
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
    ];
  },
};

export default config;
