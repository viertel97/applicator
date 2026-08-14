"""Shared Pydantic serialization helpers for API response models.

`UtcDateTime` is a drop-in replacement for `datetime` on response-model fields.
The DB stores datetimes in naive `timestamp` columns that hold UTC wall-clock
values. Serialized without a timezone marker, the frontend's `new Date(...)`
parses them as *local* time and shifts every displayed time by the viewer's
UTC offset. Emitting an explicit UTC 'Z' makes the contract honest so clients
render the correct local time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _serialize_utc(dt: datetime) -> str:
    # Naive datetimes coming from the ORM hold UTC wall-clock values.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[
    datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="json")
]
