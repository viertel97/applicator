"""Integration tests for the MS Graph → CalendarSuggestion state machine."""
from sqlalchemy import select

from app.calendar_sync.sync import MS_GRAPH, sync_calendar_events
from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
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


def _get_suggestion(db, eid="e1"):
    return db.execute(
        select(CalendarSuggestion).where(CalendarSuggestion.external_id == eid)
    ).scalar_one()


def test_new_event_creates_pending_suggestion(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["created"] == 1
    s = _get_suggestion(db_session)
    assert s.status == CalendarSuggestionStatus.pending
    assert s.external_source == MS_GRAPH
    assert s.subject == "Interview with Acme"
    assert s.location == "Zoom"
    assert s.starts_at.hour == 10 and s.ends_at.hour == 11
    assert s.suggested_application_id == app.id  # matched by organizer domain
    # No interview is created yet.
    assert db_session.execute(select(Interaction)).scalar_one_or_none() is None


def test_full_body_captured_with_links_not_truncated_preview(db_session, auth_user):
    """The whole appointment description must be stored, keeping links (Teams
    etc.). bodyPreview strips links and truncates, so body.content wins."""
    _, user = auth_user
    _app(db_session, user)
    teams = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc"
    full = f'<html><body>Join here: <a href="{teams}">Teams</a></body></html>'
    ev = _event(bodyPreview="Join here: Teams", body={"contentType": "html", "content": full})

    sync_calendar_events(db_session, user, [ev])

    s = _get_suggestion(db_session)
    assert s.body == full
    assert teams in s.body  # the join link survived


def test_body_falls_back_to_preview_when_no_full_body(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)

    sync_calendar_events(db_session, user, [_event(bodyPreview="See you then")])

    assert _get_suggestion(db_session).body == "See you then"


def test_online_meeting_join_url_used_when_no_location(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    ev = _event(location={"displayName": ""}, onlineMeeting={"joinUrl": "https://meet/x"})

    sync_calendar_events(db_session, user, [ev])

    assert _get_suggestion(db_session).location == "https://meet/x"


def test_pending_suggestion_refreshed_on_update(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    original_id = _get_suggestion(db_session).id

    stats = sync_calendar_events(
        db_session,
        user,
        [_event(subject="Rescheduled",
                start={"dateTime": "2026-08-21T14:00:00.0000000", "timeZone": "UTC"},
                end={"dateTime": "2026-08-21T15:00:00.0000000", "timeZone": "UTC"})],
    )

    assert stats["updated"] == 1 and stats["created"] == 0
    db_session.expire_all()
    s = _get_suggestion(db_session)
    assert s.id == original_id  # same row, not a duplicate
    assert s.subject == "Rescheduled" and s.starts_at.day == 21


def test_new_event_without_applications_still_stages_unmatched(db_session, auth_user):
    _, user = auth_user  # no applications

    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["created"] == 1
    s = _get_suggestion(db_session)
    assert s.suggested_application_id is None  # nothing to match to


def test_event_missing_start_is_skipped(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)

    stats = sync_calendar_events(db_session, user, [_event(start=None)])

    assert stats["skipped"] == 1 and stats["created"] == 0


def test_removed_pending_event_deletes_suggestion(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])

    stats = sync_calendar_events(
        db_session, user, [{"id": "e1", "@removed": {"reason": "deleted"}}]
    )

    assert stats["deleted"] == 1
    assert db_session.execute(
        select(CalendarSuggestion).where(CalendarSuggestion.external_id == "e1")
    ).scalar_one_or_none() is None


def test_dismissed_event_is_not_resurrected(db_session, auth_user):
    _, user = auth_user
    _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    s.status = CalendarSuggestionStatus.dismissed
    db_session.commit()

    # A full re-sync sends the same event again.
    stats = sync_calendar_events(db_session, user, [_event()])

    assert stats["skipped"] == 1 and stats["created"] == 0
    db_session.expire_all()
    assert _get_suggestion(db_session).status == CalendarSuggestionStatus.dismissed


def test_confirmed_event_updates_linked_interaction(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    # Simulate confirm: create the live-linked interview + mark confirmed.
    from app.db.models import (
        ApplicationEvent,
        ApplicationEventKind,
        InteractionChannel,
        InteractionCreatedFrom,
        InteractionDirection,
    )
    it = Interaction(
        application_id=app.id,
        occurred_at=s.starts_at,
        ends_at=s.ends_at,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        location=s.location,
        subject=s.subject,
        body=s.body,
        needs_review=False,
        created_from=InteractionCreatedFrom.graph_sync,
        external_source=MS_GRAPH,
        external_id=s.external_id,
    )
    db_session.add(it)
    db_session.flush()
    db_session.add(ApplicationEvent(
        application_id=app.id,
        kind=ApplicationEventKind.interview_scheduled,
        interaction_id=it.id,
    ))
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db_session.commit()

    stats = sync_calendar_events(
        db_session, user,
        [_event(start={"dateTime": "2026-08-22T09:00:00.0000000", "timeZone": "UTC"},
                end={"dateTime": "2026-08-22T09:30:00.0000000", "timeZone": "UTC"})],
    )

    assert stats["updated"] == 1
    db_session.expire_all()
    it2 = db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one()
    assert it2.occurred_at.day == 22 and it2.ends_at.hour == 9


def test_removed_confirmed_event_deletes_interaction(db_session, auth_user):
    _, user = auth_user
    app = _app(db_session, user)
    sync_calendar_events(db_session, user, [_event()])
    s = _get_suggestion(db_session)
    from app.db.models import (
        InteractionChannel,
        InteractionCreatedFrom,
        InteractionDirection,
    )
    it = Interaction(
        application_id=app.id, occurred_at=s.starts_at,
        direction=InteractionDirection.in_, channel=InteractionChannel.interview,
        needs_review=False, created_from=InteractionCreatedFrom.graph_sync,
        external_source=MS_GRAPH, external_id=s.external_id,
    )
    db_session.add(it)
    db_session.flush()
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db_session.commit()

    stats = sync_calendar_events(
        db_session, user, [{"id": "e1", "@removed": {"reason": "deleted"}}]
    )

    assert stats["deleted"] == 1
    db_session.expire_all()
    assert db_session.execute(
        select(Interaction).where(Interaction.external_id == "e1")
    ).scalar_one_or_none() is None
