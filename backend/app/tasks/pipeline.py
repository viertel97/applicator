from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Callable, Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.crawler.fetcher import HybridFetcher
from app.db.models import Application, FailedStage, JobState
from app.db.session import get_engine
from app.llm.base import LLMClient
from app.llm.groq import GroqClient
from app.pipeline import run_crawl, run_extract, run_generate
import httpx
from app.tasks.celery_app import celery_app


# Indirection points for tests to override
def _db_factory() -> Callable[[], Iterator[Session]]:
    factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)

    @contextmanager
    def cm() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    return cm


def _settings() -> Settings:
    return get_settings()


def _llm(settings: Settings) -> LLMClient:
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _fetcher() -> HybridFetcher:
    return HybridFetcher()


def _record_failure(db: Session, app: Application, stage: FailedStage, exc: Exception) -> None:
    app.job_state = JobState.failed
    app.failed_stage = stage
    app.job_error = str(exc)[:1000]
    db.commit()


@celery_app.task(
    name="pipeline.crawl",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2, "countdown": 10},
)
def crawl_task(self, app_id: str) -> dict:
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            raw_path, fetch_result = run_crawl(db, app, _fetcher(), settings)
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.crawl, exc)
            raise
        return {
            "app_id": app_id,
            "raw_path": str(raw_path),
            "text": fetch_result.text,
        }


@celery_app.task(name="pipeline.extract", bind=True)
def extract_task(self, payload: dict) -> dict:
    if payload.get("skipped"):
        return payload
    app_id = payload["app_id"]
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            run_extract(db, app, payload["text"], payload["raw_path"], _llm(settings))
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.extract, exc)
            raise
    return {"app_id": app_id}


@celery_app.task(name="pipeline.extract_from_text", bind=True)
def extract_from_text_task(self, app_id: str, raw_text: str) -> dict:
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            run_extract(db, app, raw_text, "pasted", _llm(settings))
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.extract, exc)
            raise
    return {"app_id": app_id}


@celery_app.task(name="pipeline.generate", bind=True)
def generate_task(self, app_id: str) -> dict:
    settings = _settings()
    cm = _db_factory()
    with cm() as db:
        app = db.get(Application, uuid.UUID(app_id))
        if app is None:
            return {"app_id": app_id, "skipped": True}
        try:
            run_generate(db, app, _llm(settings), settings)
        except Exception as exc:
            db.rollback()
            with cm() as db2:
                app2 = db2.get(Application, uuid.UUID(app_id))
                if app2:
                    _record_failure(db2, app2, FailedStage.generate, exc)
            raise
    return {"app_id": app_id}


import logging as _logging

_notify_logger = _logging.getLogger(__name__)


@celery_app.task(
    name="pipeline.notify",
    bind=False,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 5},
)
def notify_task(payload: dict, chat_id: int | None = None) -> dict:
    if chat_id is None:
        return payload
    if payload.get("skipped"):
        return payload
    token = _settings().telegram_bot_token
    if not token:
        return payload
    settings = _settings()
    app_id = payload.get("app_id")
    text = "Done"
    if app_id:
        cm = _db_factory()
        with cm() as db:
            app = db.get(Application, uuid.UUID(app_id))
            if app and app.job_posting and app.job_posting.title:
                text = f"Done: {app.job_posting.title}"
        link = f"{settings.frontend_origin}/applications/{app_id}"
        text = f"{text}\n{link}"
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        ).raise_for_status()
    except Exception as exc:
        _notify_logger.warning("Telegram notify failed: %s", exc)
        raise
    return payload
