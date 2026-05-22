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
    from app.db.models import Label
    full_kwargs = {
        "contact": {"name": "j"},
        "salary": "x", "deadline": "x", "requirements": "x", "description": "x",
        "tech_stack": ["x"], "benefits": ["x"], "required_documents": ["x"],
        "work_mode": "x", "seniority": "x",
    }
    jp = _row(db, **full_kwargs)
    label = Label(name="Y", color="#fff")
    db.add(label); db.flush()
    jp.application.labels.append(label)
    db.commit()
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
    # Assign a label so suggested_labels isn't requested either.
    from app.db.models import Label
    label = Label(name="X", color="#fff")
    db.add(label); db.flush()
    jp.application.labels.append(label)
    db.commit()
    fake_extract = MagicMock()
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    fake_extract.assert_not_called()


def test_pick_missing_includes_suggested_labels_when_app_has_none(db_session):
    db = db_session
    jp = _row(db)
    missing = pick_missing(jp)
    assert "suggested_labels" in missing


def test_pick_missing_skips_suggested_labels_when_app_already_labeled(db_session):
    db = db_session
    from app.db.models import Label
    jp = _row(db)
    label = Label(name="Tech", color="#fff")
    db.add(label); db.flush()
    jp.application.labels.append(label)
    db.commit()
    missing = pick_missing(jp)
    assert "suggested_labels" not in missing


def test_pick_missing_skips_suggested_labels_when_already_attempted(db_session):
    db = db_session
    jp = _row(db, backfill_attempts={"suggested_labels": "2026-05-01T00:00:00+00:00"})
    missing = pick_missing(jp)
    assert "suggested_labels" not in missing


def test_process_row_upserts_labels_from_extract(db_session):
    db = db_session
    from app.db.models import Label
    jp = _row(db)
    fake_extract = MagicMock(return_value={
        "suggested_labels": ["Tech", "Startup"],
        "contact": None,
        "salary": None,
        "deadline": None,
        "tech_stack": None,
        "benefits": None,
        "required_documents": None,
        "work_mode": None,
        "seniority": None,
        "requirements": None,
        "description": None,
    })
    process_row(db, jp, MagicMock(), extract_fn=fake_extract)
    db.refresh(jp.application)
    names = {lab.name for lab in jp.application.labels}
    assert names == {"Tech", "Startup"}
    assert "suggested_labels" in jp.backfill_attempts
    # Re-running should not duplicate
    db.query(Label).count() == 2


def test_adaptive_sleep_triggers_when_remaining_below_threshold(monkeypatch):
    from app.llm.base import RateLimit
    from app.tasks import backfill as bf

    sleeps: list[float] = []
    monkeypatch.setattr(bf.time, "sleep", lambda s: sleeps.append(s))

    llm = MagicMock()
    llm.last_rate_limit.return_value = RateLimit(
        limit_tokens=8000, remaining_tokens=200, reset_tokens_s=3.0,
    )
    bf._adaptive_sleep(llm)
    assert sleeps == [3.5]


def test_adaptive_sleep_noop_when_remaining_high(monkeypatch):
    from app.llm.base import RateLimit
    from app.tasks import backfill as bf

    sleeps: list[float] = []
    monkeypatch.setattr(bf.time, "sleep", lambda s: sleeps.append(s))

    llm = MagicMock()
    llm.last_rate_limit.return_value = RateLimit(
        limit_tokens=8000, remaining_tokens=7000, reset_tokens_s=3.0,
    )
    bf._adaptive_sleep(llm)
    assert sleeps == []


def test_adaptive_sleep_noop_when_provider_has_no_rate_limit(monkeypatch):
    from app.tasks import backfill as bf

    sleeps: list[float] = []
    monkeypatch.setattr(bf.time, "sleep", lambda s: sleeps.append(s))

    llm = MagicMock()
    llm.last_rate_limit.return_value = None
    bf._adaptive_sleep(llm)
    assert sleeps == []
