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


def _interview(db, user, *, needs_review, subject=None, body=None):
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
            subject=subject,
            body=body,
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


def test_ics_feed_description_includes_body(client, db_session, auth_user):
    _, user = auth_user
    _interview(
        db_session,
        user,
        needs_review=False,
        subject="Interview invite",
        body="BODYMARKERXYZ",
    )
    tokens = client.get("/api/calendar/tokens").json()
    url = tokens["calendar_url"]
    token = url.rsplit("/", 1)[-1].removesuffix(".ics")
    resp = client.get(f"/api/calendar/{token}.ics")
    assert resp.status_code == 200

    # Unfold RFC5545 continuation lines so long DESCRIPTION values can be asserted
    # without worrying about fold boundaries.
    unfolded = resp.text.replace("\r\n ", "")

    # Locate the DESCRIPTION property value and assert our markers are inside it.
    desc_start = unfolded.find("DESCRIPTION:")
    assert desc_start != -1, "DESCRIPTION property missing from ICS output"
    desc_end = unfolded.find("\r\n", desc_start)
    desc_line = unfolded[desc_start:desc_end] if desc_end != -1 else unfolded[desc_start:]

    assert "BODYMARKERXYZ" in desc_line, f"body text not found in DESCRIPTION: {desc_line!r}"
    assert "Interview invite" in desc_line, f"subject not found in DESCRIPTION: {desc_line!r}"
