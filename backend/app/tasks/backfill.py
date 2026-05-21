"""On-startup backfill task: fills empty JobPosting fields from raw_text
using a targeted LLM pass, without overwriting non-null values or retrying
fields that were already attempted."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator

import redis
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Application, JobPosting
from app.db.session import get_session_factory
from app.extractor import extract_fields
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

ELIGIBLE_FIELDS = [
    "contact",
    "salary",
    "deadline",
    "tech_stack",
    "benefits",
    "required_documents",
    "work_mode",
    "seniority",
    "requirements",
    "description",
]
_RATE_LIMIT_SLEEP = 1.0
_LOCK_KEY = "backfill:lock"
_LOCK_TTL = 3600


ExtractFn = Callable[[str, list[str], object], dict]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def pick_missing(jp: JobPosting) -> list[str]:
    attempted = set(jp.backfill_attempts or {})
    return [
        f for f in ELIGIBLE_FIELDS
        if _is_empty(getattr(jp, f)) and f not in attempted
    ]


def process_row(
    db: Session,
    jp: JobPosting,
    llm,
    extract_fn: ExtractFn = extract_fields,
) -> None:
    missing = pick_missing(jp)
    if not missing:
        return
    try:
        result = extract_fn(jp.raw_text, missing, llm)
    except Exception as exc:
        logger.warning("backfill LLM call failed for jp=%s: %s", jp.id, exc)
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    attempts = dict(jp.backfill_attempts or {})

    for field in missing:
        new_value = result.get(field)
        if not _is_empty(new_value) and _is_empty(getattr(jp, field)):
            setattr(jp, field, new_value)
        attempts[field] = now_iso
    jp.backfill_attempts = attempts
    db.commit()


@contextmanager
def _db() -> Iterator[Session]:
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


def _candidate_query(db: Session):
    return (
        db.query(JobPosting)
        .join(Application, Application.id == JobPosting.application_id)
        .filter(Application.deleted_at.is_(None))
        .filter(JobPosting.raw_text.isnot(None))
        .order_by(JobPosting.extracted_at.asc())
    )


def _run(llm) -> dict:
    processed = skipped = 0
    with _db() as db:
        ids = [jp.id for jp in _candidate_query(db).all()]
    for i, jp_id in enumerate(ids):
        with _db() as db:
            jp = db.get(JobPosting, jp_id)
            if jp is None:
                skipped += 1
                continue
            missing = pick_missing(jp)
            if not missing:
                skipped += 1
                continue
            process_row(db, jp, llm)
            processed += 1
        if i < len(ids) - 1:
            time.sleep(_RATE_LIMIT_SLEEP)
    return {"processed": processed, "skipped": skipped, "total": len(ids)}


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
