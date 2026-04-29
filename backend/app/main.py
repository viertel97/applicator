from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications as applications_api
from app.api import auth as auth_api
from app.api import chat as chat_api
from app.api import documents as documents_api
from app.api import interviews as interviews_api
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Applicator", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_api.router)
    app.include_router(documents_api.router)
    app.include_router(applications_api.router)
    app.include_router(chat_api.router)
    app.include_router(interviews_api.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
