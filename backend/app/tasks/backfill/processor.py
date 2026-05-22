"""Per-row backfill logic: which fields are missing, and how to write them."""

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.db.models import JobPosting
from app.extractor import extract_fields
from app.labels.upsert import upsert_and_assign_labels

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
SUGGESTED_LABELS = "suggested_labels"


ExtractFn = Callable[[str, list[str], object], dict]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def pick_missing(jp: JobPosting) -> list[str]:
    attempted = set(jp.backfill_attempts or {})
    missing = [
        f for f in ELIGIBLE_FIELDS
        if _is_empty(getattr(jp, f)) and f not in attempted
    ]
    if SUGGESTED_LABELS not in attempted and len(jp.application.labels) == 0:
        missing.append(SUGGESTED_LABELS)
    return missing


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
        if field == SUGGESTED_LABELS:
            if not _is_empty(new_value):
                upsert_and_assign_labels(db, jp.application, new_value)
        elif not _is_empty(new_value) and _is_empty(getattr(jp, field)):
            setattr(jp, field, new_value)
        attempts[field] = now_iso
    jp.backfill_attempts = attempts
    db.commit()
