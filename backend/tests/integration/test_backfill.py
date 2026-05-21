from unittest.mock import MagicMock

from app.db.models import Application, JobPosting, User
from app.tasks.backfill import (
    ELIGIBLE_FIELDS,
    pick_missing,
    process_row,
)


def _user(db):
    u = User(ms_oid="b1", email="b@x.com", display_name="B")
    db.add(u); db.flush(); return u


def _row(db, **overrides):
    u = _user(db)
    app = Application(user_id=u.id, url="https://x", url_hash="h" * 64)
    db.add(app); db.flush()
    jp = JobPosting(
        application_id=app.id,
        raw_text="some posting text",
        language="en",
    )
    for k, v in overrides.items():
        setattr(jp, k, v)
    db.add(jp); db.commit()
    return jp


def test_pick_missing_excludes_already_attempted(db_session):
    db = db_session
    jp = _row(db, salary="60k", backfill_attempts={"deadline": "2026-05-01T00:00:00+00:00"})
    missing = pick_missing(jp)
    assert "salary" not in missing
    assert "deadline" not in missing
    assert "contact" in missing


def test_pick_missing_returns_empty_when_nothing_to_do(db_session):
    db = db_session
    full_kwargs = {
        "contact": {"name": "j"},
        "salary": "x", "deadline": "x", "requirements": "x", "description": "x",
        "tech_stack": ["x"], "benefits": ["x"], "required_documents": ["x"],
        "work_mode": "x", "seniority": "x",
    }
    jp = _row(db, **full_kwargs)
    assert pick_missing(jp) == []


def test_process_row_writes_only_non_null_and_stamps_all(db_session):
    db = db_session
    jp = _row(db)
    llm = MagicMock()
    fake_extract = MagicMock(return_value={
        "contact": {"name": "Jane", "role": None, "email": None, "phone": None},
        "salary": None,
        "deadline": "2026-06-01",
    })
    # process_row must accept extract_fn keyword to override the real LLM call
    from app.tasks.backfill import process_row
    process_row(db, jp, llm, extract_fn=fake_extract)
    db.refresh(jp)
    assert jp.contact == {"name": "Jane", "role": None, "email": None, "phone": None}
    assert jp.salary is None
    assert jp.deadline == "2026-06-01"
    assert "contact" in jp.backfill_attempts
    assert "salary" in jp.backfill_attempts
    assert "deadline" in jp.backfill_attempts


def test_process_row_does_not_overwrite_existing(db_session):
    db = db_session
    jp = _row(db, salary="60k existing")
    fake_extract = MagicMock(return_value={"salary": "999k"})
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    db.refresh(jp)
    assert jp.salary == "60k existing"


def test_process_row_skips_when_no_missing(db_session):
    db = db_session
    full_kwargs = {
        "contact": {"name": "x"},
        "salary": "x", "deadline": "x", "requirements": "x", "description": "x",
        "tech_stack": ["x"], "benefits": ["x"], "required_documents": ["x"],
        "work_mode": "x", "seniority": "x",
    }
    jp = _row(db, **full_kwargs)
    fake_extract = MagicMock()
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    fake_extract.assert_not_called()
