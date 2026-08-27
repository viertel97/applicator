"""API tests for calendar suggestion review (list / confirm / dismiss)."""
from sqlalchemy import select

from app.calendar_sync.sync import MS_GRAPH
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
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


def _suggestion(db, user, app=None, *, eid="e1"):
    from datetime import datetime
    s = CalendarSuggestion(
        user_id=user.id,
        external_source=MS_GRAPH,
        external_id=eid,
        status=CalendarSuggestionStatus.pending,
        subject="Interview",
        starts_at=datetime(2026, 9, 1, 10, 0),
        ends_at=datetime(2026, 9, 1, 11, 0),
        location="Zoom",
        suggested_application_id=(app.id if app else None),
        match_score=0.9 if app else 0.0,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_returns_only_pending(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    _suggestion(db_session, user, app, eid="e1")
    dismissed = _suggestion(db_session, user, app, eid="e2")
    dismissed.status = CalendarSuggestionStatus.dismissed
    db_session.commit()

    r = client.get("/api/calendar/suggestions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["external_id"] == "e1"
    assert data[0]["suggested_application"]["company"] == "Acme GmbH"
    assert data[0]["match_score"] == 0.9


def test_confirm_promotes_to_live_linked_interview(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    s = _suggestion(db_session, user, app)

    r = client.post(f"/api/calendar/suggestions/{s.id}/confirm", json={})
    assert r.status_code == 200

    db_session.expire_all()
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.application_id == app.id
    assert it.channel == InteractionChannel.interview
    assert it.created_from == InteractionCreatedFrom.graph_sync
    assert it.needs_review is False
    assert it.external_source == MS_GRAPH  # live-linked
    ev = db_session.execute(
        select(ApplicationEvent).where(
            ApplicationEvent.kind == ApplicationEventKind.interview_scheduled
        )
    ).scalar_one()
    assert ev.interaction_id == it.id
    s2 = db_session.get(CalendarSuggestion, s.id)
    assert s2.status == CalendarSuggestionStatus.confirmed
    assert s2.interaction_id == it.id


def test_confirm_with_application_override(client, db_session, auth_user):
    _, user = auth_user
    matched = _app(db_session, user, company="Acme GmbH")
    other = Application(user_id=user.id, url="https://other.example/9", url_hash="o" * 64)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    s = _suggestion(db_session, user, matched)

    r = client.post(
        f"/api/calendar/suggestions/{s.id}/confirm",
        json={"application_id": str(other.id)},
    )
    assert r.status_code == 200

    db_session.expire_all()
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.application_id == other.id


def test_confirm_unmatched_without_app_is_rejected(client, db_session, auth_user):
    _, user = auth_user
    s = _suggestion(db_session, user, app=None)  # unmatched

    r = client.post(f"/api/calendar/suggestions/{s.id}/confirm", json={})
    assert r.status_code == 400

    db_session.expire_all()
    assert db_session.get(CalendarSuggestion, s.id).status == CalendarSuggestionStatus.pending


def test_dismiss_marks_dismissed(client, db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    s = _suggestion(db_session, user, app)

    r = client.post(f"/api/calendar/suggestions/{s.id}/dismiss")
    assert r.status_code == 200

    db_session.expire_all()
    assert db_session.get(CalendarSuggestion, s.id).status == CalendarSuggestionStatus.dismissed
