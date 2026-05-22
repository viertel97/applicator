"""Celery entrypoint for the on-startup backfill."""

import logging

import redis

from app.config import get_settings
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

from .query import _run

logger = logging.getLogger(__name__)

_LOCK_KEY = "backfill:lock"
_LOCK_TTL = 3600


@celery_app.task(name="tasks.backfill_missing")
def backfill_missing_task() -> dict:
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None) or settings.celery_broker_url
    client = redis.Redis.from_url(redis_url)
    lock = client.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        logger.info("backfill_missing: another run holds the lock; skipping")
        return {"status": "skipped_locked"}
    try:
        llm = GroqClient(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
        return _run(llm)
    finally:
        try:
            lock.release()
        except Exception:
            logger.warning("backfill_missing: failed to release lock")
