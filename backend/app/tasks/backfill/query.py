"""Candidate selection and run loop for the backfill task."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting
from app.db.session import get_session_factory

from .pacing import _adaptive_sleep
from .processor import pick_missing, process_row


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
    for jp_id in ids:
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
        _adaptive_sleep(llm)
    return {"processed": processed, "skipped": skipped, "total": len(ids)}
