import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import applications as applications_api
from app.api import auth as auth_api
from app.api import bot as bot_api
from app.api import calendar as calendar_api
from app.api import chat as chat_api
from app.api import discard_reasons as discard_reasons_api
from app.api import webhooks as webhooks_api
from app.api import documents as documents_api
from app.api import inquiry_prompt as inquiry_prompt_api
from app.api import interactions as interactions_api
from app.api import labels as labels_api
from app.config import get_settings
from app.db import events as db_events
from app.services import stats as stats_api
from app.services import stats_detail as stats_detail_api
from app.tasks.backfill import backfill_missing_task
from app.tasks.categorize_labels import categorize_existing_labels_task

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        backfill_missing_task.apply_async()
        logger.info("backfill_missing enqueued on startup")
    except Exception as exc:
        logger.warning("failed to enqueue backfill on startup: %s", exc)
    try:
        categorize_existing_labels_task.apply_async()
        logger.info("categorize_existing_labels enqueued on startup")
    except Exception as exc:
        logger.warning("failed to enqueue categorize on startup: %s", exc)
    yield


def create_app() -> FastAPI:
    db_events.register()
    settings = get_settings()
    app = FastAPI(title="Applicator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_api.router)
    app.include_router(calendar_api.router)
    app.include_router(documents_api.router)
    app.include_router(applications_api.router)
    app.include_router(bot_api.router)
    app.include_router(chat_api.router)
    app.include_router(interactions_api.router)
    app.include_router(labels_api.router)
    app.include_router(inquiry_prompt_api.router)
    app.include_router(discard_reasons_api.router)
    app.include_router(stats_api.router)
    app.include_router(stats_detail_api.router)
    app.include_router(webhooks_api.router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
