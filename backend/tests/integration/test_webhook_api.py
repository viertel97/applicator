import uuid
from unittest.mock import patch
from app.db.models import Application, JobPosting, Interaction, InteractionChannel
from app.email_ingest.interview_extract import ExtractedInterview


def _app(db, user, company, host):
    app = Application(user_id=user.id, url=f"https://{host}/jobs/1", url_hash=uuid.uuid4().hex)
    db.add(app); db.flush()
    db.add(JobPosting(application_id=app.id, raw_text="x", company=company))
    db.commit()
    return app


def _fake_extract(subject, body, llm):
    from datetime import datetime, timezone
    return ExtractedInterview(starts_at=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
                              interview_stage="technical", location="https://meet/x",
                              contact_name="Jane", contact_handle="jane@acme.example")


def test_webhook_creates_needs_review_interview(app_client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "seedtok"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client.post(
            "/api/webhooks/inbound-email/seedtok",
            json={"from": "jane@acme.example", "subject": "Interview at Acme", "body_text": "..."},
        )
    assert resp.status_code == 202, resp.text
    it = db_session.query(Interaction).filter_by(application_id=app.id).one()
    assert it.needs_review is True
    assert it.channel == InteractionChannel.interview
    assert it.location == "https://meet/x"


def test_webhook_unknown_token_404(app_client):
    resp = app_client.post("/api/webhooks/inbound-email/nope",
                           json={"from": "x@y.z", "subject": "s", "body_text": "b"})
    assert resp.status_code == 404


def test_webhook_no_applications_returns_202_no_orphan(app_client, db_session, auth_user):
    _, user = auth_user
    user.ingest_token = "tok2"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client.post("/api/webhooks/inbound-email/tok2",
                               json={"from": "x@y.z", "subject": "s", "body_text": "b"})
    assert resp.status_code == 202
    assert db_session.query(Interaction).count() == 0
