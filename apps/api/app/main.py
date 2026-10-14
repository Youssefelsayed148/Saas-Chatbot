from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analytics.handoff import router as handoff_analytics_router
from app.analytics.router import router as analytics_router
from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.bots.router import router as bots_router
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router
from app.conversations.router import router as conversations_router
from app.core.config import get_settings, validate_startup_settings
from app.core.errors import REQUEST_ID_HEADER, RequestIdMiddleware, install_error_handlers
from app.followups.router import router as followups_router
from app.inbox.listing import router as inbox_listing_router
from app.inbox.router import router as inbox_router
from app.knowledge.router import router as knowledge_router
from app.platform.router import router as platform_router
from app.provisioning.router import router as provisioning_router
from app.tenants.router import router as tenants_router
from app.widget.router import router as widget_router

# Same-origin deployment (web + api under one gateway in production). Local dev uses
# localhost origins on the default port; a narrow allowlist, not a wildcard,
# because cookies carry authentication.
CORS_ALLOW_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    # Startup guard (P4-00): refuse a forbidden configuration, e.g. the
    # offline stub model with environment=production.
    validate_startup_settings(get_settings())
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
    application.include_router(tenants_router)
    application.include_router(bots_router)
    application.include_router(knowledge_router)
    application.include_router(chat_router)
    application.include_router(conversations_router)
    application.include_router(followups_router)
    application.include_router(contacts_router)
    application.include_router(inbox_router)
    application.include_router(inbox_listing_router)
    application.include_router(analytics_router)
    application.include_router(handoff_analytics_router)
    application.include_router(widget_router)
    application.include_router(platform_router)
    application.include_router(provisioning_router)
    install_error_handlers(application)
    return application


app = create_app()
