"""Idempotent projection of MS Graph calendar events into Interactions.

Mirrors the email-webhook ingest path: each event becomes an interview
`Interaction`, matched to a best-guess application and flagged
``needs_review`` so it surfaces in the existing review queue. Re-runs
converge — events are keyed on ``(external_source, external_id)``.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
    JobPosting,
    User,
)
from app.email_ingest.interview_match import Candidate, match_application

MS_GRAPH = "ms_graph"


def _parse_dt(node: dict | None) -> datetime | None:
    """Parse a Graph ``{"dateTime": ..., "timeZone": ...}`` node to naive UTC.

    Graph returns fractional seconds (7 digits) that ``fromisoformat`` chokes
    on, so truncate to whole seconds. Values are requested in UTC via the
    Prefer header, so we drop the (assumed-UTC) zone and store naive.
    """
    if not node:
        return None
    raw = node.get("dateTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:19])
    except ValueError:
        return None


def _location(ev: dict) -> str | None:
    loc = (ev.get("location") or {}).get("displayName")
    if loc:
        return loc
    return (ev.get("onlineMeeting") or {}).get("joinUrl")


def _organizer_email(ev: dict) -> str:
    return (
        (ev.get("organizer") or {}).get("emailAddress", {}).get("address", "")
    )


def _candidates(db: Session, user: User) -> list[Candidate]:
    rows = db.execute(
        select(Application, JobPosting)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(Application.user_id == user.id, Application.deleted_at.is_(None))
    ).all()
    return [
        Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
        for a, jp in rows
    ]


def _delete_event(db: Session, external_id: str) -> bool:
    it = db.execute(
        select(Interaction).where(
            Interaction.external_source == MS_GRAPH,
            Interaction.external_id == external_id,
        )
    ).scalar_one_or_none()
    if it is None:
        return False
    # ON DELETE CASCADE on ApplicationEvent.interaction_id removes the
    # linked interview_scheduled timeline note.
    db.delete(it)
    return True


def sync_calendar_events(db: Session, user: User, events: list[dict]) -> dict:
    """Upsert/delete Interactions for the given Graph delta events.

    Returns a stats dict: created / updated / deleted / skipped.
    """
    stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
    candidates = _candidates(db, user)

    for ev in events:
        external_id = ev.get("id")
        if not external_id:
            stats["skipped"] += 1
            continue

        # @removed → cancelled event: drop the mirrored interview.
        if ev.get("@removed") is not None:
            if _delete_event(db, external_id):
                stats["deleted"] += 1
            else:
                stats["skipped"] += 1
            continue

        start = _parse_dt(ev.get("start"))
        if start is None:
            # No usable start time — nothing meaningful to schedule.
            stats["skipped"] += 1
            continue

        end = _parse_dt(ev.get("end"))
        location = _location(ev)
        subject = ev.get("subject")
        body = ev.get("bodyPreview")

        existing = db.execute(
            select(Interaction).where(
                Interaction.external_source == MS_GRAPH,
                Interaction.external_id == external_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            # Update: refresh time/location/subject; keep the existing link.
            existing.occurred_at = start
            existing.ends_at = end
            existing.location = location
            existing.subject = subject
            existing.body = body
            stats["updated"] += 1
            continue

        if not candidates:
            # No applications to link to (FK is non-null). Same effective
            # behaviour as the webhook path's "no applications".
            stats["skipped"] += 1
            continue

        app_id, _score = match_application(
            sender=_organizer_email(ev),
            subject=subject or "",
            body=body or "",
            candidates=candidates,
        )
        it = Interaction(
            application_id=_uuid.UUID(app_id),
            occurred_at=start,
            ends_at=end,
            direction=InteractionDirection.in_,
            channel=InteractionChannel.interview,
            location=location,
            subject=subject,
            body=body,
            needs_review=True,
            created_from=InteractionCreatedFrom.graph_sync,
            external_source=MS_GRAPH,
            external_id=external_id,
        )
        db.add(it)
        db.flush()  # assign it.id so the timeline note can link to it
        db.add(
            ApplicationEvent(
                application_id=_uuid.UUID(app_id),
                kind=ApplicationEventKind.interview_scheduled,
                interaction_id=it.id,
            )
        )
        stats["created"] += 1

    db.commit()
    return stats
