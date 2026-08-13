import uuid
from datetime import datetime, timezone

from app.db.models import (
    Application,
    JobPosting,
    Interaction,
    InteractionChannel,
    InteractionDirection,
    InterviewStage,
)


def _interview(db, user, *, needs_review):
    app = Application(user_id=user.id, url="https://acme.example/j", url_hash=uuid.uuid4().hex)
    db.add(app)
    db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company="Acme"))
    db.add(
        Interaction(
            application_id=app.id,
            occurred_at=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
            direction=InteractionDirection.in_,
            channel=InteractionChannel.interview,
            interview_stage=InterviewStage.technical,
            needs_review=needs_review,
        )
    )
    db.commit()


def test_ics_feed_includes_confirmed_excludes_review(client, db_session, auth_user):
    _, user = auth_user
    _interview(db_session, user, needs_review=False)
    _interview(db_session, user, needs_review=True)
    tokens = client.get("/api/calendar/tokens").json()
    url = tokens["calendar_url"]
    token = url.rsplit("/", 1)[-1].removesuffix(".ics")
    resp = client.get(f"/api/calendar/{token}.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    body = resp.text
    assert body.count("BEGIN:VEVENT") == 1  # only the confirmed one
    assert "SUMMARY:Acme" in body


def test_ics_feed_unknown_token_404(app_client):
    resp = app_client.get("/api/calendar/deadbeef.ics")
    assert resp.status_code == 404
