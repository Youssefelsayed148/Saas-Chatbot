"""Stable error format and request-id plumbing (docs/05).

Every error response is ``{"error": {"code", "message", "request_id"}}``.
Codes are stable strings; messages are specific but never leak internals.
"""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class ApiError(Exception):
    """Raise from services/routers to produce the stable error format."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(
    request: Request,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    request_id = getattr(request.state, "request_id", "") or uuid4().hex
    error: dict[str, object] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return {"error": error}


def install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        # Visitors never see internal cap names (RAG limits are staff-only detail).
        public = request.url.path.startswith("/api/public/")
        details = None if public and exc.code == "QUOTA_EXCEEDED" else exc.details
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(request, exc.code, exc.message, details),
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Stable generic message; per-field details so forms can show messages
        # under the matching input. Only the dotted location (without the
        # request-body root) and the message are included: never echo input,
        # context, docs URLs or any other value that could carry a submitted
        # secret (password, token, message body).
        fields = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
                "message": str(error.get("msg", "Value is invalid.")),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                request, "VALIDATION_ERROR", "Request body failed validation.", {"fields": fields}
            ),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body(request, "INTERNAL_ERROR", "Unexpected server error."),
        )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, echoes it as a response header, exposes it via request.state."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = request.headers.get(REQUEST_ID_HEADER, "") or uuid4().hex
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response
