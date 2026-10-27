import { NextResponse, type NextRequest } from "next/server";

/**
 * Upload guard for the same-origin API proxy (P2-02, docs/06) plus the
 * per-bot frame-ancestors CSP for the widget frame page (A2.2, #33).
 *
 * The proxy forwards /api requests to the FastAPI process. Next's headers()
 * config and the backend's own limits apply downstream, but the proxy must
 * refuse oversized multipart bodies BEFORE spending the bandwidth/storage:
 * a Content-Length above the maximum PLACEHOLDER cap (25 MB x 20 files,
 * plus multipart overhead; 520 MB total) is rejected here with 413. Missing/absent Content-Length (chunked bodies)
 * cannot be validated here and fall through to the API's streaming check.
 *
 * headers() in next.config is static, so the per-bot CSP is computed here:
 * the frame route cannot set response headers itself, and the fetch to the
 * public locator endpoint (below) is the only data the pipeline needs. The
 * static /widget/:path* rule stays as the permissive fallback for loads
 * where the API is unreachable or the locator is missing/unknown — denying
 * sessions for unlisted page origins (DOMAIN_NOT_ALLOWED) still applies
 * inside the frame.
 */

const MAX_ACCEPTED_BODY_BYTES = 520 * 1024 * 1024;

// Same target the rewrites in next.config.ts point at the FastAPI process.
const apiOrigin = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

async function frameAncestorsHeader(locator: string): Promise<string | null> {
  try {
    const response = await fetch(
      `${apiOrigin}/api/public/v1/widgets/${encodeURIComponent(
        locator,
      )}/frame-ancestors`,
      {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(2500),
      },
    );
    if (!response.ok) return null;
    const payload = (await response.json()) as { frame_ancestors?: string };
    const value = payload.frame_ancestors?.trim();
    if (!value) return null;
    // Header injection guard: the value must be a CSP source list only.
    return /^[\w.:/ *'?-]+$/.test(value) ? `frame-ancestors ${value}` : null;
  } catch {
    // API unreachable (cold start, deploy): keep the static permissive rule.
    return null;
  }
}

export async function proxy(request: NextRequest) {
  const length = request.headers.get("content-length");
  const isApiPath = request.nextUrl.pathname.startsWith("/api/");
  if (isApiPath && length) {
    const size = Number(length);
    if (Number.isFinite(size) && size > MAX_ACCEPTED_BODY_BYTES) {
      return new NextResponse(
        JSON.stringify({
          error: {
            code: "FILE_TOO_LARGE",
            message: "The request body exceeds the allowed upload size.",
          },
        }),
        { status: 413, headers: { "content-type": "application/json" } },
      );
    }
  }
  if (
    request.method === "GET" &&
    request.nextUrl.pathname === "/widget/frame"
  ) {
    const locator = request.nextUrl.searchParams.get("locator");
    if (locator) {
      const value = await frameAncestorsHeader(locator);
      if (value) {
        const response = NextResponse.next();
        response.headers.set("Content-Security-Policy", value);
        return response;
      }
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/:path*", "/widget/frame"],
};
