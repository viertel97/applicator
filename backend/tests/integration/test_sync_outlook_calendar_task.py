"""Integration tests for the Outlook calendar sync task orchestration."""
from sqlalchemy import select

from app.calendar_sync.graph import DeltaExpired
from app.config import get_settings
from app.db.models import Application, CalendarSyncState, Interaction, JobPosting
from app.tasks.sync_outlook_calendar import (
    sync_outlook_calendar_task,
    sync_user_calendar,
)


class FakeGraph:
    """Scriptable stand-in for GraphClient."""

    def __init__(self, calendar_id="cal-1", pages=None, expire_first=False):
        self.calendar_id = calendar_id
        # pages: mapping of delta_link (None for full) -> (events, next_delta)
        self.pages = pages or {None: ([], "delta-1")}
        self.expire_first = expire_first
        self.calls: list = []

    def resolve_calendar_id(self, name):
        return self.calendar_id

    def delta_events(self, calendar_id, delta_link=None):
        self.calls.append(delta_link)
        if self.expire_first and delta_link is not None:
            self.expire_first = False
            raise DeltaExpired()
        return self.pages.get(delta_link, ([], "delta-latest"))


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


def test_sync_user_calendar_full_then_persists_delta(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    graph = FakeGraph(pages={None: ([_event()], "delta-A")})

    stats = sync_user_calendar(db_session, user, get_settings(), graph=graph)

    assert stats["created"] == 1
    st = db_session.execute(
        select(CalendarSyncState).where(CalendarSyncState.user_id == user.id)
    ).scalar_one()
    assert st.calendar_id == "cal-1"
    assert st.delta_link == "delta-A"
    assert graph.calls == [None]  # started from a full sync


def test_sync_user_calendar_uses_stored_delta_link(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    db_session.add(
        CalendarSyncState(user_id=user.id, calendar_id="cal-1", delta_link="stored")
    )
    db_session.commit()
    graph = FakeGraph(pages={"stored": ([_event()], "delta-B")})

    sync_user_calendar(db_session, user, get_settings(), graph=graph)

    assert graph.calls == ["stored"]
    st = db_session.execute(
        select(CalendarSyncState).where(CalendarSyncState.user_id == user.id)
    ).scalar_one()
    assert st.delta_link == "delta-B"


def test_sync_user_calendar_resets_on_delta_expired(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    db_session.add(
        CalendarSyncState(user_id=user.id, calendar_id="cal-1", delta_link="stale")
    )
    db_session.commit()
    graph = FakeGraph(pages={None: ([_event()], "delta-fresh")}, expire_first=True)

    stats = sync_user_calendar(db_session, user, get_settings(), graph=graph)

    # First call used the stale link (410), second call was a full re-sync.
    assert graph.calls == ["stale", None]
    assert stats["created"] == 1
    st = db_session.execute(
        select(CalendarSyncState).where(CalendarSyncState.user_id == user.id)
    ).scalar_one()
    assert st.delta_link == "delta-fresh"


def test_sync_user_calendar_skips_when_no_calendar(db_session, auth_user):
    _, user = auth_user
    graph = FakeGraph(calendar_id=None)

    stats = sync_user_calendar(db_session, user, get_settings(), graph=graph)

    assert stats == {"skipped": "no_calendar"}


def test_task_skips_when_oauth_disabled(monkeypatch):
    from app.tasks import sync_outlook_calendar as mod

    class _S:
        oauth_enabled = False

    monkeypatch.setattr(mod, "get_settings", lambda: _S())
    assert sync_outlook_calendar_task.run() == {"skipped": "oauth_disabled"}
