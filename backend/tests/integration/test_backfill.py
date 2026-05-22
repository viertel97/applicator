import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.db.models import Application, JobPosting, JobState, LabelCategory, User
from app.tasks.backfill.processor import process_row


def _row(db):
    """Create a minimal Application + JobPosting for backfill testing."""
    u = User(ms_oid="backfill-test", email="backfill@test.example", display_name="Backfill")
    db.add(u)
    db.flush()
    app = Application(url="https://test.example/job", url_hash="a" * 64, user_id=u.id)
    app.id = uuid.uuid4()
    app.job_state = JobState.extracted
    app.language = "de"
    app.labels = []
    db.add(app)
    db.flush()
    jp = JobPosting(
        application_id=app.id,
        raw_text="Job description text",
        title="Dev",
        company="Acme",
        language="de",
    )
    db.add(jp)
    db.commit()
    db.refresh(jp)
    db.refresh(app)
    jp.application  # load relationship
    return jp


def test_process_row_upserts_labels_from_extract(db_session):
    db = db_session
    jp = _row(db)
    fake_extract = MagicMock(return_value={
        "suggested_labels": {
            "role": ["AI Engineer"],
            "tech": ["Python"],
            "company_size": ["Konzern"],
        },
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
    by_name = {lab.name: lab for lab in jp.application.labels}
    assert by_name["AI Engineer"].category == LabelCategory.role
    assert by_name["Python"].category == LabelCategory.tech
    assert by_name["Konzern"].category == LabelCategory.company_size
    assert "suggested_labels" in jp.backfill_attempts
