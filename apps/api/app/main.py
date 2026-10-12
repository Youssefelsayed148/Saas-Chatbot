from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.core.errors import REQUEST_ID_HEADER, RequestIdMiddleware, install_error_handlers

# Same-origin deployment (web + api under one gateway in production). Local dev uses
# localhost origins on the default port; a narrow allowlist, not a wildcard,
# because cookies carry authentication.
CORS_ALLOW_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    application = FastAPI(title="Website Chatbot SaaS API", version="0.2.0")
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[REQUEST_ID_HEADER, "Content-Type", "X-CSRF-Token"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    install_error_handlers(application)
    return application


app = create_app()
