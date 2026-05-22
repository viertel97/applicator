"""Worker-startup task that assigns categories to legacy `other` labels."""

import logging

import redis

from app.config import get_settings
from app.db.models import Label, LabelCategory
from app.db.session import get_session_factory
from app.labels.categorize import categorize_names, iter_batches
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_LOCK_KEY = "labels:categorize:lock"
_LOCK_TTL = 3600


def _build_groq_client() -> GroqClient:
    settings = get_settings()
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _candidate_names(db) -> list[str]:
    rows = (
        db.query(Label.name)
        .filter(Label.category == LabelCategory.other)
        .filter(Label.is_auto.is_(True))
        .all()
    )
    return [r[0] for r in rows]


def _apply_batch(db, mapping: dict[str, LabelCategory]) -> int:
    updated = 0
    for name, category in mapping.items():
        lab = (
            db.query(Label)
            .filter(Label.name == name)
            .filter(Label.category == LabelCategory.other)
            .filter(Label.is_auto.is_(True))
            .first()
        )
        if lab is None:
            continue
        lab.category = category
        updated += 1
    db.commit()
    return updated


@celery_app.task(name="tasks.categorize_existing_labels")
def categorize_existing_labels_task() -> dict:
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None) or settings.celery_broker_url
    client = redis.Redis.from_url(redis_url)
    lock = client.lock(_LOCK_KEY, timeout=_LOCK_TTL, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        logger.info("categorize_existing_labels: locked; skipping")
        return {"status": "skipped_locked"}
    try:
        llm = _build_groq_client()
        session_factory = get_session_factory()
        db = session_factory()
        try:
            names = _candidate_names(db)
            if not names:
                return {"updated": 0, "batches": 0, "total": 0}
            total_updated = 0
            batch_count = 0
            for batch in iter_batches(names):
                try:
                    mapping = categorize_names(batch, llm)
                except Exception as exc:
                    logger.warning("categorize: batch failed: %s", exc)
                    continue
                if mapping:
                    total_updated += _apply_batch(db, mapping)
                batch_count += 1
            return {
                "updated": total_updated,
                "batches": batch_count,
                "total": len(names),
            }
        finally:
            db.close()
    finally:
        try:
            lock.release()
        except Exception:
            logger.warning("categorize_existing_labels: failed to release lock")
