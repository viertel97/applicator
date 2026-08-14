from sqlalchemy import inspect

from app.db.models import WebhookRequest


def test_webhook_request_has_expected_columns():
    cols = {c.key for c in inspect(WebhookRequest).columns}
    assert {
        "id",
        "user_id",
        "ingest_token",
        "source_ip",
        "headers",
        "raw_body",
        "status",
        "reason",
        "matched_application_id",
        "created_at",
    } <= cols


def test_webhook_request_tablename():
    assert WebhookRequest.__tablename__ == "webhook_request"


def test_webhook_request_nullability():
    cols = WebhookRequest.__table__.columns
    assert cols["user_id"].nullable is True
    assert cols["matched_application_id"].nullable is True
    assert cols["ingest_token"].nullable is False
    assert cols["status"].nullable is False


def test_webhook_request_construction_defaults():
    r = WebhookRequest(ingest_token="tok", status="ignored")
    assert r.ingest_token == "tok"
    assert r.status == "ignored"
    assert r.user_id is None
    assert r.matched_application_id is None
