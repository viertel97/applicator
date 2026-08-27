"""API tests for Outlook sync visibility: sync-status, sync-now, entries."""
from datetime import datetime

from app.calendar_sync.sync import MS_GRAPH
from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    JobPosting,
)


def _app(db, user, *, company="Acme GmbH"):
    a = Application(user_id=user.id, url="https://acme.example/1", url_hash="a" * 64)
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company=company))
    db.commit()
    db.refresh(a)
    return a


def _suggestion(db, user, app=None, *, eid, status, body=None):
    s = CalendarSuggestion(
        user_id=user.id,
        external_source=MS_GRAPH,
        external_id=eid,
        status=status,
        subject="Interview",
        starts_at=datetime(2026, 9, 1, 10, 0),
        ends_at=datetime(2026, 9, 1, 11, 0),
        location="Zoom",
        body=body,
        organizer_email="hr@acme.example",
        suggested_application_id=(app.id if app else None),
        match_score=0.9 if app else None,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_sync_status_returns_health_and_oauth_flag(client, db_session, auth_user):
    _, user = auth_user
    user.outlook_last_sync_at = datetime(2026, 8, 27, 9, 0)
    user.outlook_last_status = "ok"
    user.outlook_last_trigger = "scheduled"
    user.outlook_last_counts = {"created": 1, "updated": 0, "deleted": 0, "skipped": 0}
    db_session.commit()

    r = client.get("/api/calendar/sync-status")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "ok"
    assert data["last_counts"]["created"] == 1
    assert "oauth_enabled" in data


def test_entries_returns_all_statuses(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    _suggestion(db_session, user, app, eid="e1", status=CalendarSuggestionStatus.pending)
    _suggestion(db_session, user, app, eid="e2", status=CalendarSuggestionStatus.confirmed)
    _suggestion(db_session, user, None, eid="e3", status=CalendarSuggestionStatus.dismissed)

    r = client.get("/api/calendar/entries")
    assert r.status_code == 200
    data = r.json()
    statuses = {row["status"] for row in data}
    assert statuses == {"pending", "confirmed", "dismissed"}
    ext = next(row for row in data if row["external_id"] == "e1")
    assert ext["suggested_application"]["company"] == "Acme GmbH"


def test_suggestions_returns_full_body_with_links(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    teams = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc"
    body = f'<html><body>Join: <a href="{teams}">Teams</a></body></html>'
    _suggestion(
        db_session, user, app, eid="e1",
        status=CalendarSuggestionStatus.pending, body=body,
    )

    r = client.get("/api/calendar/suggestions")
    assert r.status_code == 200
    row = next(x for x in r.json() if x["external_id"] == "e1")
    assert row["body"] == body
    assert teams in row["body"]


def test_sync_now_oauth_disabled_returns_skipped_200(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod

    class _S:
        oauth_enabled = False

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "skipped"
    assert data["last_reason"] == "oauth_disabled"
    assert data["last_trigger"] == "manual"


def test_sync_now_runs_sync_and_returns_health(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod
    from app.tasks.sync_outlook_calendar import _record_health

    class _S:
        oauth_enabled = True

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    def _fake_sync(db, user, settings, *, trigger):
        _record_health(
            user, status="ok", trigger=trigger,
            counts={"created": 2, "updated": 0, "deleted": 0, "skipped": 0},
        )
        db.commit()
        return {"created": 2}

    monkeypatch.setattr(cal_mod, "sync_user_calendar", _fake_sync)

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "ok"
    assert data["last_trigger"] == "manual"
    assert data["last_counts"]["created"] == 2


def test_sync_now_broken_connection_returns_200_not_500(client, db_session, auth_user, monkeypatch):
    from app.api import calendar as cal_mod
    from app.tasks.sync_outlook_calendar import _record_health

    class _S:
        oauth_enabled = True

    monkeypatch.setattr(cal_mod, "get_settings", lambda: _S())

    def _boom(db, user, settings, *, trigger):
        _record_health(
            user, status="error", reason="graph_error", trigger=trigger, error="boom",
        )
        db.commit()
        raise RuntimeError("boom")

    monkeypatch.setattr(cal_mod, "sync_user_calendar", _boom)

    r = client.post("/api/calendar/sync-now")
    assert r.status_code == 200
    data = r.json()
    assert data["last_status"] == "error"
    assert data["last_reason"] == "graph_error"
