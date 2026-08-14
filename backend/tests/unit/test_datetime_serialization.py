"""API datetime fields must serialize as UTC-aware ISO (trailing 'Z').

Regression guard: naive datetimes stored in the DB hold UTC wall-clock values.
If the API emits them without a timezone marker, the frontend `new Date(...)`
parses them as *local* time, shifting every displayed time by the viewer's UTC
offset (the "interview shows 2h early" bug in UTC+2).
"""

import uuid
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder

from app.api.calendar import CalendarInterview


def _calendar_interview(dt):
    return CalendarInterview(
        id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        display_id=1,
        company="Acme",
        starts_at=dt,
        ends_at=dt,
        location=None,
        interview_stage=None,
        needs_review=False,
    )


def test_naive_datetime_serializes_as_utc_z():
    # A naive datetime is what the ORM yields for a `timestamp` column; it holds UTC.
    enc = jsonable_encoder(_calendar_interview(datetime(2026, 8, 15, 12, 0, 0)))
    assert enc["starts_at"] == "2026-08-15T12:00:00Z"
    assert enc["ends_at"] == "2026-08-15T12:00:00Z"


def test_aware_datetime_serializes_as_utc_z():
    enc = jsonable_encoder(
        _calendar_interview(datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc))
    )
    assert enc["starts_at"] == "2026-08-15T12:00:00Z"
