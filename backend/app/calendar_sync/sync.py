"""Idempotent projection of MS Graph calendar events into CalendarSuggestions.

Pulled events are STAGED, not applied: each event becomes a CalendarSuggestion
(status='pending') keyed on (external_source, external_id). Confirmation into a
real interview happens elsewhere (the confirm endpoint). Once confirmed, this
sync keeps the linked Interaction in step with Outlook (live-link); once
dismissed, the event is never resurrected. Re-runs converge.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    Interaction,
    JobPosting,
    User,
)
from app.email_ingest.interview_match import Candidate, match_application

MS_GRAPH = "ms_graph"


def _parse_dt(node: dict | None) -> datetime | None:
    """Parse a Graph ``{"dateTime": ...}`` node to naive UTC (whole seconds)."""
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
    return (ev.get("organizer") or {}).get("emailAddress", {}).get("address", "")


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


def _linked_interaction(db: Session, external_id: str) -> Interaction | None:
    return db.execute(
        select(Interaction).where(
            Interaction.external_source == MS_GRAPH,
            Interaction.external_id == external_id,
        )
    ).scalar_one_or_none()


def sync_calendar_events(db: Session, user: User, events: list[dict]) -> dict:
    """Upsert/delete CalendarSuggestions for the given Graph delta events.

    Returns a stats dict: created / updated / deleted / skipped.
    """
    stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
    candidates = None  # lazily computed only when we create a new suggestion

    for ev in events:
        external_id = ev.get("id")
        if not external_id:
            stats["skipped"] += 1
            continue

        existing = db.execute(
            select(CalendarSuggestion).where(
                CalendarSuggestion.user_id == user.id,
                CalendarSuggestion.external_source == MS_GRAPH,
                CalendarSuggestion.external_id == external_id,
            )
        ).scalar_one_or_none()

        # Cancellation.
        if ev.get("@removed") is not None:
            if existing is None:
                stats["skipped"] += 1
            elif existing.status == CalendarSuggestionStatus.pending:
                db.delete(existing)
                stats["deleted"] += 1
            elif existing.status == CalendarSuggestionStatus.confirmed:
                it = _linked_interaction(db, external_id)
                if it is not None:
                    db.delete(it)  # CASCADE removes the timeline note
                db.delete(existing)
                stats["deleted"] += 1
            else:  # dismissed
                stats["skipped"] += 1
            continue

        start = _parse_dt(ev.get("start"))
        if start is None:
            stats["skipped"] += 1
            continue

        end = _parse_dt(ev.get("end"))
        location = _location(ev)
        subject = ev.get("subject")
        body = ev.get("bodyPreview")

        if existing is None:
            if candidates is None:
                candidates = _candidates(db, user)
            organizer_email = _organizer_email(ev)
            app_id, score = match_application(
                sender=organizer_email,
                subject=subject or "",
                body=body or "",
                candidates=candidates,
            )
            db.add(
                CalendarSuggestion(
                    user_id=user.id,
                    external_source=MS_GRAPH,
                    external_id=external_id,
                    status=CalendarSuggestionStatus.pending,
                    subject=subject,
                    starts_at=start,
                    ends_at=end,
                    location=location,
                    body=body,
                    organizer_email=organizer_email,
                    suggested_application_id=(
                        uuid.UUID(app_id) if app_id else None
                    ),
                    match_score=score,
                )
            )
            stats["created"] += 1
            continue

        if existing.status == CalendarSuggestionStatus.dismissed:
            stats["skipped"] += 1
            continue

        if existing.status == CalendarSuggestionStatus.pending:
            existing.subject = subject
            existing.starts_at = start
            existing.ends_at = end
            existing.location = location
            existing.body = body
            existing.organizer_email = _organizer_email(ev)
            stats["updated"] += 1
            continue

        # confirmed → live-link: keep the promoted interview in step.
        if existing.status == CalendarSuggestionStatus.confirmed:
            it = _linked_interaction(db, external_id)
            if it is not None:
                it.occurred_at = start
                it.ends_at = end
                it.location = location
                it.subject = subject
                it.body = body
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            # Unknown/future status — skip rather than silently mishandle.
            stats["skipped"] += 1

    db.commit()
    return stats
