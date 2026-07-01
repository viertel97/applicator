"""Integration tests for GET /api/stats/detail."""
import uuid
from datetime import UTC, datetime, timedelta

from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    ApplicationStatus,
    JobPosting,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app(db, user, status=ApplicationStatus.applied, created_at=None):
    key = uuid.uuid4().hex
    kwargs = dict(
        user_id=user.id,
        url=f"https://x.test/{key}",
        url_hash=key,
        status=status,
    )
    if created_at is not None:
        kwargs["created_at"] = created_at
    a = Application(**kwargs)
    db.add(a)
    db.flush()
    return a


def _status_event(db, app, to_value, occurred_at=None):
    ev = ApplicationEvent(
        application_id=app.id,
        kind=ApplicationEventKind.status_change,
        from_value=None,
        to_value=to_value,
        occurred_at=occurred_at or datetime.now(UTC),
    )
    db.add(ev)
    db.flush()
    return ev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_smoke_and_outcomes(client, db_session, auth_user):
    """Endpoint returns 200; outcomes partition correctly across statuses."""
    _, u = auth_user

    _app(db_session, u, ApplicationStatus.applied)
    _app(db_session, u, ApplicationStatus.applied)
    _app(db_session, u, ApplicationStatus.rejected)
    _app(db_session, u, ApplicationStatus.accepted)
    _app(db_session, u, ApplicationStatus.withdrawn)
    db_session.commit()

    r = client.get("/api/stats/detail")
    assert r.status_code == 200, r.text
    body = r.json()

    outcomes = body["outcomes"]
    assert outcomes["total"] == 5
    assert outcomes["rejected"] == 1
    assert outcomes["accepted"] == 1
    assert outcomes["withdrawn"] == 1
    # 2 applied apps are active (no terminal status)
    assert outcomes["active"] == 2
    # rejected + accepted + withdrawn + active = total
    assert (
        outcomes["active"]
        + outcomes["accepted"]
        + outcomes["offer"]
        + outcomes["rejected"]
        + outcomes["withdrawn"]
        + outcomes["discarded"]
    ) == outcomes["total"]


def test_decline_timeline_with_company_role(client, db_session, auth_user):
    """decline_timeline item includes company/role from JobPosting."""
    _, u = auth_user

    a = _app(db_session, u, ApplicationStatus.rejected)
    db_session.add(JobPosting(
        application_id=a.id,
        company="Acme Corp",
        title="Engineer",
        raw_text="some text",
    ))
    occurred = datetime.now(UTC) - timedelta(days=1)
    _status_event(db_session, a, "rejected", occurred_at=occurred)
    db_session.commit()

    r = client.get("/api/stats/detail")
    assert r.status_code == 200, r.text
    timeline = r.json()["decline_timeline"]

    assert len(timeline) >= 1
    item = next((x for x in timeline if x["app_id"] == str(a.id)), None)
    assert item is not None, "rejected app must appear in decline_timeline"
    assert item["company"] == "Acme Corp"
    assert item["role"] == "Engineer"
    assert item["kind"] == "rejected"


def test_ghost_respects_ghost_days(client, db_session, auth_user):
    """Ghost count changes with ghost_days param."""
    _, u = auth_user

    old_date = datetime.now(UTC) - timedelta(days=60)
    _app(db_session, u, ApplicationStatus.applied, created_at=old_date)
    # No incoming interaction — this app should be a ghost after 21 days
    db_session.commit()

    # Default ghost_days=21 → exactly this one app qualifies (60 days old)
    r = client.get("/api/stats/detail")
    assert r.status_code == 200, r.text
    ghost = r.json()["ghost"]
    assert ghost["count"] == 1
    assert ghost["threshold_days"] == 21

    # Very high ghost_days → app does NOT qualify
    r2 = client.get("/api/stats/detail?ghost_days=9999")
    assert r2.status_code == 200, r2.text
    ghost2 = r2.json()["ghost"]
    assert ghost2["count"] == 0
    assert ghost2["threshold_days"] == 9999


def test_date_window_filtering(client, db_session, auth_user):
    """from/to params restrict which applications are counted."""
    import sqlalchemy

    _, u = auth_user
    now = datetime.now(UTC).replace(tzinfo=None)

    # Three apps at distinct dates: ~60, ~30, and ~0 days ago.
    a_old = _app(db_session, u, ApplicationStatus.applied)
    a_mid = _app(db_session, u, ApplicationStatus.applied)
    a_new = _app(db_session, u, ApplicationStatus.applied)
    db_session.commit()

    # Force created_at via UPDATE to defeat server_default on INSERT.
    db_session.execute(
        sqlalchemy.text("UPDATE application SET created_at = :ts WHERE id = :id"),
        {"ts": now - timedelta(days=60), "id": str(a_old.id)},
    )
    db_session.execute(
        sqlalchemy.text("UPDATE application SET created_at = :ts WHERE id = :id"),
        {"ts": now - timedelta(days=30), "id": str(a_mid.id)},
    )
    db_session.execute(
        sqlalchemy.text("UPDATE application SET created_at = :ts WHERE id = :id"),
        {"ts": now - timedelta(days=0), "id": str(a_new.id)},
    )
    db_session.commit()

    # Window: ~45 days ago to ~15 days ago → only the day-30 app falls inside.
    fr = (now - timedelta(days=45)).isoformat()
    to = (now - timedelta(days=15)).isoformat()

    r = client.get("/api/stats/detail", params={"from": fr, "to": to})
    assert r.status_code == 200, r.text
    assert r.json()["outcomes"]["total"] == 1


def test_declines_weekly_entry(client, db_session, auth_user):
    """declines_weekly has an entry for the week of a rejection event."""
    _, u = auth_user

    a = _app(db_session, u, ApplicationStatus.rejected)
    event_time = datetime(2024, 6, 10, tzinfo=UTC)  # known ISO week
    _status_event(db_session, a, "rejected", occurred_at=event_time)
    db_session.commit()

    r = client.get("/api/stats/detail")
    assert r.status_code == 200, r.text
    weekly = r.json()["declines_weekly"]

    # ISO week for 2024-06-10 is 2024-W24
    week_entry = next((w for w in weekly if w["week"] == "2024-W24"), None)
    assert week_entry is not None, f"expected 2024-W24 in declines_weekly, got {weekly}"
    assert week_entry["rejected"] >= 1


def test_empty_data(client, db_session, auth_user):
    """Authenticated user with no applications gets 200 with zeroed outcomes and empty lists."""
    # No applications created — db is empty for this user.
    r = client.get("/api/stats/detail")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["outcomes"]["total"] == 0
    assert body["declines_weekly"] == []
    assert body["decline_timeline"] == []
    assert body["rejection_stage"] == [
        {"stage": "applied", "count": 0},
        {"stage": "responded", "count": 0},
        {"stage": "interview", "count": 0},
        {"stage": "offer", "count": 0},
    ]
