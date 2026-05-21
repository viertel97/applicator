from app.db.models import Application, JobPosting


def test_job_posting_has_contact_and_backfill_attempts():
    cols = {c.name for c in JobPosting.__table__.columns}
    assert "contact" in cols
    assert "backfill_attempts" in cols
    assert "contact_person" not in cols
    assert "application_email" not in cols


def test_application_has_deleted_at():
    cols = {c.name for c in Application.__table__.columns}
    assert "deleted_at" in cols
