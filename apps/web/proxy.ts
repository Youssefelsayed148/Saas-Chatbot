import { NextResponse, type NextRequest } from "next/server";

/**
 * Upload guard for the same-origin API proxy (P2-02, docs/06).
 *
 * The proxy forwards /api requests to the FastAPI process. Next's headers()
 * config and the backend's own limits apply downstream, but the proxy must
 * refuse oversized multipart bodies BEFORE spending the bandwidth/storage:
 * a Content-Length above the maximum PLACEHOLDER cap (25 MB x 20 files,
 * plus multipart overhead; 520 MB total) is rejected here with 413. Missing/absent Content-Length (chunked bodies)
 * cannot be validated here and fall through to the API's streaming check.
 */

const MAX_ACCEPTED_BODY_BYTES = 520 * 1024 * 1024;

export function proxy(request: NextRequest) {
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
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/:path*"],
};
