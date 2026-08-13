import uuid
from datetime import datetime, timedelta, timezone

from app.db.models import (
    Application,
    JobPosting,
    Interaction,
    InteractionChannel,
    InteractionDirection,
    InterviewStage,
)


def _app_with_interview(db, user, *, company, when, needs_review=False):
    app = Application(
        user_id=user.id,
        url="https://acme.example/jobs/1",
        url_hash=uuid.uuid4().hex,
    )
    db.add(app)
    db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company=company))
    it = Interaction(
        application_id=app.id,
        occurred_at=when,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        interview_stage=InterviewStage.technical,
        needs_review=needs_review,
    )
    db.add(it)
    db.commit()
    return app, it


def test_calendar_interviews_range_filter(client, db_session, auth_user):
    _, user = auth_user
    now = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    _app_with_interview(db_session, user, company="Acme", when=now)
    _app_with_interview(
        db_session, user, company="OldCo", when=now - timedelta(days=90)
    )
    resp = client.get(
        "/api/calendar/interviews",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["interview_stage"] == "technical"
    assert rows[0]["needs_review"] is False
    assert rows[0]["starts_at"].startswith("2026-08-15T10:00")


def test_calendar_interviews_requires_auth(app_client):
    resp = app_client.get("/api/calendar/interviews")
    assert resp.status_code == 401
