from fastapi import FastAPI

from app.api.health import router


def create_app() -> FastAPI:
    application = FastAPI(title="Website Chatbot SaaS API", version="0.1.0")
    application.include_router(router)
    return application


app = create_app()
