import uuid
from datetime import datetime, timezone

from app.db.models import (
    Application, ApplicationEvent, ApplicationEventKind, ApplicationStatus,
    Interaction, InteractionChannel, InteractionCreatedFrom, InteractionDirection,
)
from app.services.stats import _weekly_volume


def _app(status, created_at, aid=None):
    return Application(
        id=aid or uuid.uuid4(),
        user_id=uuid.uuid4(),
        url="u", url_hash="h",
        status=status, created_at=created_at,
    )


def _ev(aid, to_value, occurred_at):
    return ApplicationEvent(
        application_id=aid, kind=ApplicationEventKind.status_change,
        to_value=to_value, occurred_at=occurred_at,
    )


def _interaction(occurred_at, direction, created_from=InteractionCreatedFrom.manual):
    return Interaction(
        application_id=uuid.uuid4(), occurred_at=occurred_at,
        direction=direction, channel=InteractionChannel.mail,
        created_from=created_from,
    )


def _by_week(rows):
    return {r.week: r for r in rows}


def test_applied_uses_event_week_when_event_present():
    aid = uuid.uuid4()
    # created in W21, applied event in W23
    app = _app(ApplicationStatus.applied, datetime(2026, 5, 20), aid)
    ev = _ev(aid, "applied", datetime(2026, 6, 1, tzinfo=timezone.utc))  # W23
    rows = _by_week(_weekly_volume([app], [ev], [], []))
    assert rows["2026-W23"].applied == 1
    assert "2026-W21" not in rows or rows["2026-W21"].applied == 0


def test_applied_falls_back_to_created_week_without_event():
    app = _app(ApplicationStatus.applied, datetime(2026, 5, 20))  # W21, no event
    rows = _by_week(_weekly_volume([app], [], [], []))
    assert rows["2026-W21"].applied == 1


def test_pre_apply_statuses_excluded_from_applied():
    apps = [
        _app(ApplicationStatus.draft, datetime(2026, 5, 20)),
        _app(ApplicationStatus.need_call, datetime(2026, 5, 20)),
        _app(ApplicationStatus.apply_direct, datetime(2026, 5, 20)),
    ]
    rows = _by_week(_weekly_volume(apps, [], [], []))
    assert "2026-W21" not in rows or rows["2026-W21"].applied == 0


def test_apply_then_discard_appears_in_both_series():
    aid = uuid.uuid4()
    app = _app(ApplicationStatus.discarded, datetime(2026, 5, 10), aid)
    events = [
        _ev(aid, "applied", datetime(2026, 5, 20, tzinfo=timezone.utc)),    # W21
        _ev(aid, "discarded", datetime(2026, 6, 1, tzinfo=timezone.utc)),   # W23
    ]
    rows = _by_week(_weekly_volume([app], events, [], []))
    assert rows["2026-W21"].applied == 1
    assert rows["2026-W23"].discarded == 1
    # not counted as applied in W23, not discarded in W21
    assert rows["2026-W21"].discarded == 0
    assert rows["2026-W23"].applied == 0


def test_discarded_only_app_not_counted_as_applied():
    app = _app(ApplicationStatus.discarded, datetime(2026, 5, 20))  # W21, no events
    rows = _by_week(_weekly_volume([app], [], [], []))
    assert rows["2026-W21"].discarded == 1
    assert rows["2026-W21"].applied == 0


def test_responses_and_inquiries_bucketed_by_occurred_at():
    resp = _interaction(datetime(2026, 5, 20), InteractionDirection.in_)  # W21
    inq = _interaction(
        datetime(2026, 5, 21), InteractionDirection.out,
        created_from=InteractionCreatedFrom.inquiry_sent,
    )  # W21
    rows = _by_week(_weekly_volume([], [], [resp], [inq]))
    assert rows["2026-W21"].responses == 1
    assert rows["2026-W21"].inquiries == 1
