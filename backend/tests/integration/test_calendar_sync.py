"""Integration tests for the MS Graph → Interaction sync service."""
from sqlalchemy import select

from app.calendar_sync.sync import MS_GRAPH, sync_calendar_events
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    JobPosting,
)


def _app(db, user, *, url="https://acme.example/jobs/1", company="Acme GmbH"):
    a = Application(user_id=user.id, url=url, url_hash=url[-64:].rjust(64, "x"))
    db.add(a)
    db.flush()
    db.add(JobPosting(application_id=a.id, raw_text="x", company=company))
    db.commit()
    db.refresh(a)
    return a


def _event(eid="e1", **over):
    ev = {
        "id": eid,
        "subject": "Interview with Acme",
        "bodyPreview": "See you then",
        "start": {"dateTime": "2026-08-20T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-08-20T11:00:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": "Zoom"},
        "organizer": {"emailAddress": {"address": "hr@acme.example", "name": "HR"}},
    }
    ev.update(over)
    return ev


def test_created_event_becomes_interview_needs_review(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["created"] == 1
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.channel == InteractionChannel.interview
    assert it.created_from == InteractionCreatedFrom.graph_sync
    assert it.external_source == MS_GRAPH
    assert it.needs_review is True
    assert it.application_id == app.id  # matched by organizer domain
    assert it.location == "Zoom"
    assert it.occurred_at.hour == 10 and it.ends_at.hour == 11


def test_created_event_writes_timeline_note(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)

    sync_calendar_events(db_session, user, [_event()])

    ev = db_session.execute(
        select(ApplicationEvent).where(
            ApplicationEvent.kind == ApplicationEventKind.interview_scheduled
        )
    ).scalar_one()
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert ev.interaction_id == it.id


def test_online_meeting_join_url_used_when_no_location(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    ev = _event(location={"displayName": ""}, onlineMeeting={"joinUrl": "https://meet/x"})

    sync_calendar_events(db_session, user, [ev])

    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it.location == "https://meet/x"


def test_update_refreshes_fields_keeps_link(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    it = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    original_id = it.id
    original_app = it.application_id

    updated = _event(
        subject="Rescheduled",
        start={"dateTime": "2026-08-21T14:00:00.0000000", "timeZone": "UTC"},
        end={"dateTime": "2026-08-21T15:00:00.0000000", "timeZone": "UTC"},
        location={"displayName": "Office"},
    )
    stats = sync_calendar_events(db_session, user, [updated])

    assert stats["updated"] == 1 and stats["created"] == 0
    db_session.expire_all()
    it2 = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it2.id == original_id  # same row, not a duplicate
    assert it2.application_id == original_app
    assert it2.subject == "Rescheduled"
    assert it2.occurred_at.day == 21 and it2.location == "Office"


def test_removed_event_deletes_interview_and_timeline_note(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])

    stats = sync_calendar_events(
        db_session, user, [{"id": "e1", "@removed": {"reason": "deleted"}}]
    )

    assert stats["deleted"] == 1
    assert db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one_or_none() is None
    # CASCADE removed the timeline note too.
    assert db_session.execute(
        select(ApplicationEvent).where(
            ApplicationEvent.kind == ApplicationEventKind.interview_scheduled
        )
    ).scalar_one_or_none() is None


def test_sync_is_idempotent(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    events = [_event()]

    sync_calendar_events(db_session, user, events)
    stats = sync_calendar_events(db_session, user, events)

    assert stats["created"] == 0 and stats["updated"] == 1
    rows = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalars().all()
    assert len(rows) == 1  # no duplicate on re-run


def test_event_missing_start_is_skipped(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event(start=None)])

    assert stats["skipped"] == 1 and stats["created"] == 0


def test_no_applications_skips_creation(db_session, auth_user):
    _, user = auth_user  # no applications seeded

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["skipped"] == 1 and stats["created"] == 0
