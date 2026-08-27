"""User.outlook_last_* health is stamped on every sync exit path."""
import pytest

from app.calendar_sync.graph import GraphRateLimited
from app.config import get_settings
from app.db.models import Application, JobPosting
from app.tasks import sync_outlook_calendar as mod
from app.tasks.sync_outlook_calendar import sync_user_calendar


class FakeGraph:
    """Scriptable GraphClient stand-in (mirrors test_sync_outlook_calendar_task)."""

    def __init__(self, calendar_id="cal-1", events=None, delta="delta-A", raise_exc=None):
        self.calendar_id = calendar_id
        self.events = events or []
        self.delta = delta
        self.raise_exc = raise_exc

    def resolve_calendar_id(self, name):
        return self.calendar_id

    def delta_events(self, calendar_id, delta_link=None):
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.events, self.delta


def _app(db, user):
    a = Application(user_id=user.id, url="https://acme.example/j", url_hash="a" * 64)
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company="Acme GmbH"))
    db.commit()
    return a


def _event(eid="e1"):
    return {
        "id": eid,
        "subject": "Acme interview",
        "bodyPreview": "hi",
        "start": {"dateTime": "2026-08-20T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-20T11:00:00.0000000", "timeZone": "UTC"},
        "organizer": {"emailAddress": {"address": "hr@acme.example"}},
    }


def test_ok_records_counts_and_status(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(events=[_event()], delta="delta-A")

    stats = sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="manual")

    db_session.refresh(user)
    assert user.outlook_last_status == "ok"
    assert user.outlook_last_reason is None
    assert user.outlook_last_trigger == "manual"
    assert user.outlook_last_error is None
    assert user.outlook_last_counts["created"] == stats["created"]
    assert user.outlook_last_sync_at is not None


def test_no_calendar_records_skipped(db_session, auth_user):
    _, user = auth_user
    graph = FakeGraph(calendar_id=None)

    result = sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    assert result == {"skipped": "no_calendar"}
    db_session.refresh(user)
    assert user.outlook_last_status == "skipped"
    assert user.outlook_last_reason == "no_calendar"
    assert user.outlook_last_trigger == "scheduled"
    assert user.outlook_last_counts is None


def test_graph_exception_records_error_and_reraises(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(raise_exc=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "graph_error"
    assert "boom" in user.outlook_last_error
    assert user.outlook_last_counts is None


def test_rate_limited_records_error_and_reraises(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(raise_exc=GraphRateLimited(30))

    with pytest.raises(GraphRateLimited):
        sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "rate_limited"


def test_persist_failure_records_error(db_session, auth_user, monkeypatch):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(events=[_event()], delta="delta-A")

    def _boom(db, user, events):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(mod, "sync_calendar_events", _boom)

    with pytest.raises(RuntimeError):
        sync_user_calendar(db_session, user, get_settings(), graph=graph, trigger="scheduled")

    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "graph_error"
    assert "db exploded" in user.outlook_last_error


def test_no_token_records_skipped(db_session, auth_user):
    _, user = auth_user
    user.ms_refresh_token_encrypted = None
    db_session.commit()

    result = sync_user_calendar(db_session, user, get_settings(), graph=None, trigger="manual")

    assert result == {"skipped": "no_token"}
    db_session.refresh(user)
    assert user.outlook_last_status == "skipped"
    assert user.outlook_last_reason == "no_token"


def test_token_refresh_failed_records_error(db_session, auth_user, monkeypatch):
    _, user = auth_user
    user.ms_refresh_token_encrypted = "encrypted-blob"
    db_session.commit()

    monkeypatch.setattr(mod, "decrypt", lambda *a, **k: "refresh-token")
    monkeypatch.setattr(
        mod, "acquire_token_by_refresh_token",
        lambda *a, **k: {"error": "invalid_grant", "error_description": "consent revoked"},
    )

    result = sync_user_calendar(db_session, user, get_settings(), graph=None, trigger="manual")

    assert result == {"skipped": "token_refresh_failed"}
    db_session.refresh(user)
    assert user.outlook_last_status == "error"
    assert user.outlook_last_reason == "token_refresh_failed"
    assert user.outlook_last_error
