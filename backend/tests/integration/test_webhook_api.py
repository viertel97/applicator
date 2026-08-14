import uuid
from unittest.mock import patch
import pytest
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


def test_webhook_records_row_on_created(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    _, user = auth_user
    app = _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "rectok"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()):
        resp = app_client.post(
            "/api/webhooks/inbound-email/rectok",
            json={"from": "jane@acme.example", "subject": "Interview at Acme", "body_text": "..."},
        )
    assert resp.status_code == 202, resp.text
    row = db_session.query(WebhookRequest).filter_by(ingest_token="rectok").one()
    assert row.status == "created"
    assert row.reason is None
    assert row.user_id == user.id
    assert row.matched_application_id == app.id
    assert row.raw_body is not None
    assert isinstance(row.headers, dict)


def test_webhook_records_row_on_no_match(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    _, user = auth_user
    _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "nmtok"; db_session.commit()
    db_session.refresh(user)
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()), \
         patch("app.api.webhooks.match_application", return_value=(None, 0.0)):
        resp = app_client.post(
            "/api/webhooks/inbound-email/nmtok",
            json={"from": "x@y.z", "subject": "s", "body_text": "b"},
        )
    assert resp.status_code == 202, resp.text
    row = db_session.query(WebhookRequest).filter_by(ingest_token="nmtok").one()
    assert row.status == "ignored"
    assert row.reason == "no match"
    assert row.matched_application_id is None


def test_webhook_records_row_on_bad_token(app_client, db_session):
    from app.db.models import WebhookRequest

    resp = app_client.post(
        "/api/webhooks/inbound-email/badtok",
        json={"from": "x@y.z", "subject": "s", "body_text": "b"},
    )
    assert resp.status_code == 404
    row = db_session.query(WebhookRequest).filter_by(ingest_token="badtok").one()
    assert row.status == "not_found"
    assert row.user_id is None


def test_webhook_records_row_on_unexpected_error(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    _, user = auth_user
    _app(db_session, user, "Acme GmbH", "acme.example")
    user.ingest_token = "errtok"; db_session.commit()
    db_session.refresh(user)

    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    # TestClient re-raises server exceptions (raise_server_exceptions=True),
    # so the RuntimeError propagates out of the POST call.
    with patch("app.api.webhooks.extract_interview", _fake_extract), \
         patch("app.api.webhooks._webhook_llm", return_value=object()), \
         patch("app.api.webhooks.match_application", _boom), \
         pytest.raises(RuntimeError):
        app_client.post(
            "/api/webhooks/inbound-email/errtok",
            json={"from": "x@y.z", "subject": "s", "body_text": "b"},
        )

    # The request transaction may be aborted; drop any pending state before
    # issuing a fresh read on the audit row committed by the handler's finally.
    db_session.rollback()
    row = db_session.query(WebhookRequest).filter_by(ingest_token="errtok").one()
    assert row.status == "error"
    assert row.reason == "RuntimeError"


def test_list_requests_returns_owned_rows_only(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    client, user = auth_user
    # Owned row.
    db_session.add(WebhookRequest(
        ingest_token="own", user_id=user.id, status="ignored", reason="no match",
        raw_body='{"from": "jane@acme.example", "subject": "Hi"}',
    ))
    # Invalid-token row (user_id null) — must NOT appear in per-user list.
    db_session.add(WebhookRequest(
        ingest_token="bad", user_id=None, status="not_found", reason="unknown token",
    ))
    db_session.commit()

    resp = client.get("/api/webhooks/requests")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "ignored"
    assert r["reason"] == "no match"
    assert r["from"] == "jane@acme.example"
    assert r["subject"] == "Hi"


def test_get_request_detail_and_ownership(app_client, db_session, auth_user):
    from app.db.models import WebhookRequest

    client, user = auth_user
    owned = WebhookRequest(
        ingest_token="own", user_id=user.id, status="created",
        headers={"x-test": "1"}, raw_body='{"from": "a@b.c"}',
    )
    other = WebhookRequest(ingest_token="oth", user_id=None, status="not_found")
    db_session.add_all([owned, other]); db_session.commit()
    db_session.refresh(owned); db_session.refresh(other)

    ok = client.get(f"/api/webhooks/requests/{owned.id}")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["headers"] == {"x-test": "1"}
    assert body["raw_body"] == '{"from": "a@b.c"}'
    assert body["from"] == "a@b.c"

    # Not owned → 404.
    denied = client.get(f"/api/webhooks/requests/{other.id}")
    assert denied.status_code == 404


def test_list_requests_handles_object_from(app_client, db_session, auth_user):
    """Some providers send `from` as an object, not a string.

    The summary schema types `from` as str|None, so the read endpoint must
    coerce it (to the email) instead of 500ing on the whole list.
    """
    from app.db.models import WebhookRequest

    client, user = auth_user
    db_session.add(WebhookRequest(
        ingest_token="objfrom", user_id=user.id, status="ignored", reason="no match",
        raw_body='{"from": {"email": "onboarding@inboxbridge.io", "name": ""},'
                 ' "subject": "Welcome"}',
    ))
    db_session.commit()

    resp = client.get("/api/webhooks/requests")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["from"] == "onboarding@inboxbridge.io"
    assert rows[0]["subject"] == "Welcome"
