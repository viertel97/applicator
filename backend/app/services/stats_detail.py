"""Pure metric functions and HTTP layer for detailed application statistics.

Pure functions operate over preloaded ORM row lists and return Pydantic models.
The router/endpoint at the bottom handles DB access and wires everything together.
"""
from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    ApplicationStatus,
    Interaction,
    InteractionChannel,
    InteractionDirection,
    JobPosting,
    User,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

WEEK_FMT = "%G-W%V"  # ISO-week bucket

DECLINE_VALUES = ("rejected", "withdrawn", "discarded")

APPLIED_SET = {
    ApplicationStatus.applied,
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
    ApplicationStatus.accepted,
    ApplicationStatus.withdrawn,
    ApplicationStatus.interview,
}

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class Outcomes(BaseModel):
    active: int
    accepted: int
    offer: int
    rejected: int
    withdrawn: int
    discarded: int
    total: int


class DeclineWeek(BaseModel):
    week: str
    rejected: int
    withdrawn: int
    discarded: int


class DeclineTimelineItem(BaseModel):
    app_id: str
    company: str | None
    role: str | None
    kind: str  # one of DECLINE_VALUES
    occurred_at: datetime
    stage_reached: str  # "applied" | "responded" | "interview" | "offer"


class RejectionStage(BaseModel):
    stage: str
    count: int


class MeanMedian(BaseModel):
    mean: float | None
    median: float | None


class Velocity(BaseModel):
    applied_to_response_h: MeanMedian
    response_to_interview_h: MeanMedian
    interview_to_offer_h: MeanMedian
    offer_to_decision_h: MeanMedian


class Ghost(BaseModel):
    count: int
    threshold_days: int


class Interview(BaseModel):
    reached: int
    won: int
    lost: int
    win_rate: float | None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _naive(dt: datetime) -> datetime:
    """Strip timezone info to produce a naive-UTC datetime."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _decline_of(
    app: Application,
    status_events: list[ApplicationEvent],
) -> tuple[str, datetime] | None:
    """Return (kind, occurred) for a declined application, or None."""
    kind = app.status.value
    if kind not in DECLINE_VALUES:
        return None

    # Find the earliest status_change event with to_value == kind for this app
    candidates = [
        _naive(e.occurred_at)
        for e in status_events
        if (
            e.application_id == app.id
            and e.kind == ApplicationEventKind.status_change
            and e.to_value == kind
        )
    ]
    if candidates:
        occurred = min(candidates)
    else:
        occurred = _naive(app.created_at)

    return (kind, occurred)


def _stage_reached(
    app_id: uuid.UUID,
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
    before: datetime | None = None,
) -> str:
    """Return the furthest stage reached, optionally only considering evidence before `before`.

    Precedence: offer > interview > responded > applied.
    """

    def _is_before(dt: datetime) -> bool:
        if before is None:
            return True
        return _naive(dt) < before

    # offer: status_change event to_value == "offer"
    for e in status_events:
        if (
            e.application_id == app_id
            and e.kind == ApplicationEventKind.status_change
            and e.to_value == "offer"
            and _is_before(e.occurred_at)
        ):
            return "offer"

    # interview: status_change event to_value == "interview" OR interaction channel==interview
    for e in status_events:
        if (
            e.application_id == app_id
            and e.kind == ApplicationEventKind.status_change
            and e.to_value == "interview"
            and _is_before(e.occurred_at)
        ):
            return "interview"

    for it in interactions:
        if (
            it.application_id == app_id
            and it.channel == InteractionChannel.interview
            and _is_before(it.occurred_at)
        ):
            return "interview"

    # responded: any interaction with direction == in_
    for it in interactions:
        if (
            it.application_id == app_id
            and it.direction == InteractionDirection.in_
            and _is_before(it.occurred_at)
        ):
            return "responded"

    return "applied"


def _applied_at(
    app: Application,
    status_events: list[ApplicationEvent],
) -> datetime:
    """Return the applied_at timestamp (naive UTC): earliest applied event or created_at."""
    candidates = [
        _naive(e.occurred_at)
        for e in status_events
        if (
            e.application_id == app.id
            and e.kind == ApplicationEventKind.status_change
            and e.to_value == "applied"
        )
    ]
    return min(candidates) if candidates else _naive(app.created_at)


def _mean_median(samples: list[float]) -> MeanMedian:
    """Compute mean and median, rounded to 1 decimal, or None if no samples."""
    if not samples:
        return MeanMedian(mean=None, median=None)
    return MeanMedian(
        mean=round(sum(samples) / len(samples), 1),
        median=round(statistics.median(samples), 1),
    )


# ---------------------------------------------------------------------------
# Public metric functions
# ---------------------------------------------------------------------------


def compute_outcomes(apps: list[Application]) -> Outcomes:
    """Count application outcomes across all apps."""
    total = len(apps)
    accepted = sum(1 for a in apps if a.status == ApplicationStatus.accepted)
    offer = sum(1 for a in apps if a.status == ApplicationStatus.offer)
    rejected = sum(1 for a in apps if a.status == ApplicationStatus.rejected)
    withdrawn = sum(1 for a in apps if a.status == ApplicationStatus.withdrawn)
    discarded = sum(1 for a in apps if a.status == ApplicationStatus.discarded)
    active = total - (accepted + offer + rejected + withdrawn + discarded)
    return Outcomes(
        active=active,
        accepted=accepted,
        offer=offer,
        rejected=rejected,
        withdrawn=withdrawn,
        discarded=discarded,
        total=total,
    )


def compute_declines_weekly(
    apps: list[Application],
    status_events: list[ApplicationEvent],
) -> list[DeclineWeek]:
    """Bucket declined applications by ISO week of their decline event."""
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rejected": 0, "withdrawn": 0, "discarded": 0}
    )

    for app in apps:
        result = _decline_of(app, status_events)
        if result is None:
            continue
        kind, occurred = result
        week = occurred.strftime(WEEK_FMT)
        buckets[week][kind] += 1

    return [
        DeclineWeek(week=w, **counts)
        for w, counts in sorted(buckets.items())
    ]


def compute_decline_timeline(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
    postings: dict[uuid.UUID, tuple[str | None, str | None]],
    limit: int = 25,
) -> list[DeclineTimelineItem]:
    """Build a timeline of recent declines, sorted by occurred_at DESC."""
    items: list[DeclineTimelineItem] = []

    for app in apps:
        result = _decline_of(app, status_events)
        if result is None:
            continue
        kind, occurred = result
        company, role = postings.get(app.id, (None, None))
        stage = _stage_reached(app.id, status_events, interactions, before=occurred)
        items.append(
            DeclineTimelineItem(
                app_id=str(app.id),
                company=company,
                role=role,
                kind=kind,
                occurred_at=occurred,
                stage_reached=stage,
            )
        )

    items.sort(key=lambda x: x.occurred_at, reverse=True)
    return items[:limit]


def compute_rejection_stage(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
) -> list[RejectionStage]:
    """Count declined apps per stage reached, always returning all 4 stages."""
    stage_order = ["applied", "responded", "interview", "offer"]
    counts: dict[str, int] = {s: 0 for s in stage_order}

    for app in apps:
        result = _decline_of(app, status_events)
        if result is None:
            continue
        _kind, occurred = result
        stage = _stage_reached(app.id, status_events, interactions, before=occurred)
        counts[stage] += 1

    return [RejectionStage(stage=s, count=counts[s]) for s in stage_order]


def compute_velocity(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
) -> Velocity:
    """Compute mean/median hour-deltas between pipeline stages across all apps."""
    applied_to_response: list[float] = []
    response_to_interview: list[float] = []
    interview_to_offer: list[float] = []
    offer_to_decision: list[float] = []

    for app in apps:
        app_events = [
            e
            for e in status_events
            if e.application_id == app.id and e.kind == ApplicationEventKind.status_change
        ]
        app_interactions = [it for it in interactions if it.application_id == app.id]

        # applied_at
        applied = _applied_at(app, app_events)

        # response_at: earliest incoming interaction
        in_interactions = [
            _naive(it.occurred_at)
            for it in app_interactions
            if it.direction == InteractionDirection.in_
        ]
        response = min(in_interactions) if in_interactions else None

        # interview_at: earliest of interview event OR interview interaction
        interview_candidates: list[datetime] = []
        for e in app_events:
            if e.to_value == "interview":
                interview_candidates.append(_naive(e.occurred_at))
        for it in app_interactions:
            if it.channel == InteractionChannel.interview:
                interview_candidates.append(_naive(it.occurred_at))
        interview = min(interview_candidates) if interview_candidates else None

        # offer_at: earliest offer event
        offer_candidates = [
            _naive(e.occurred_at) for e in app_events if e.to_value == "offer"
        ]
        offer = min(offer_candidates) if offer_candidates else None

        # decision_at: earliest accepted/rejected/withdrawn event
        decision_candidates = [
            _naive(e.occurred_at)
            for e in app_events
            if e.to_value in {"accepted", "rejected", "withdrawn"}
        ]
        decision = min(decision_candidates) if decision_candidates else None

        # Build samples (only when both endpoints present AND end >= start)
        def _hours(start: datetime, end: datetime) -> float | None:
            delta = (end - start).total_seconds() / 3600
            return delta if delta >= 0 else None

        if response is not None:
            h = _hours(applied, response)
            if h is not None:
                applied_to_response.append(h)

        if response is not None and interview is not None:
            h = _hours(response, interview)
            if h is not None:
                response_to_interview.append(h)

        if interview is not None and offer is not None:
            h = _hours(interview, offer)
            if h is not None:
                interview_to_offer.append(h)

        if offer is not None and decision is not None:
            h = _hours(offer, decision)
            if h is not None:
                offer_to_decision.append(h)

    return Velocity(
        applied_to_response_h=_mean_median(applied_to_response),
        response_to_interview_h=_mean_median(response_to_interview),
        interview_to_offer_h=_mean_median(interview_to_offer),
        offer_to_decision_h=_mean_median(offer_to_decision),
    )


def compute_ghost(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
    ghost_days: int,
) -> Ghost:
    """Count apps in APPLIED_SET with no incoming interaction and applied_at <= threshold."""
    now = _naive(datetime.now(UTC))
    threshold = now - timedelta(days=ghost_days)

    # Build set of app_ids that have at least one incoming interaction
    has_response: set[uuid.UUID] = {
        it.application_id
        for it in interactions
        if it.direction == InteractionDirection.in_
    }

    count = 0
    for app in apps:
        if app.status not in APPLIED_SET:
            continue
        if app.id in has_response:
            continue
        applied = _applied_at(app, [e for e in status_events if e.application_id == app.id])
        if applied <= threshold:
            count += 1

    return Ghost(count=count, threshold_days=ghost_days)


def compute_interview(
    apps: list[Application],
    status_events: list[ApplicationEvent],
    interactions: list[Interaction],
) -> Interview:
    """Compute interview funnel: reached, won, lost, win_rate."""
    # Build lookup structures
    events_by_app: dict[uuid.UUID, list[ApplicationEvent]] = defaultdict(list)
    for e in status_events:
        if e.kind == ApplicationEventKind.status_change:
            events_by_app[e.application_id].append(e)

    interview_interactions: set[uuid.UUID] = {
        it.application_id
        for it in interactions
        if it.channel == InteractionChannel.interview
    }

    reached: set[uuid.UUID] = set()
    for app in apps:
        app_evs = events_by_app[app.id]
        has_interview_event = any(e.to_value == "interview" for e in app_evs)
        if (
            has_interview_event
            or app.id in interview_interactions
            or app.status == ApplicationStatus.interview
        ):
            reached.add(app.id)

    won = 0
    lost = 0
    app_by_id = {app.id: app for app in apps}

    for aid in reached:
        app = app_by_id.get(aid)
        app_evs = events_by_app[aid]

        # won: offer/accepted event OR offer/accepted status
        is_won = False
        if app and app.status in (ApplicationStatus.offer, ApplicationStatus.accepted):
            is_won = True
        if not is_won:
            is_won = any(e.to_value in {"offer", "accepted"} for e in app_evs)

        # lost: rejected event OR rejected status
        is_lost = False
        if not is_won:
            if app and app.status == ApplicationStatus.rejected:
                is_lost = True
            if not is_lost:
                is_lost = any(e.to_value == "rejected" for e in app_evs)

        if is_won:
            won += 1
        elif is_lost:
            lost += 1

    total_decided = won + lost
    win_rate = won / total_decided if total_decided > 0 else None

    return Interview(reached=len(reached), won=won, lost=lost, win_rate=win_rate)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class DetailOut(BaseModel):
    outcomes: Outcomes
    declines_weekly: list[DeclineWeek]
    decline_timeline: list[DeclineTimelineItem]
    rejection_stage: list[RejectionStage]
    velocity: Velocity
    ghost: Ghost
    interview: Interview


router = APIRouter(prefix="/api/stats", tags=["stats"])


def _between(col, fr: datetime | None, to: datetime | None) -> list:
    out = []
    if fr is not None:
        out.append(col >= fr)
    if to is not None:
        out.append(col <= to)
    return out


@router.get("/detail", response_model=DetailOut)
def detail(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    fr: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: datetime | None = Query(default=None),  # noqa: B008
    ghost_days: int = Query(default=21),  # noqa: B008
) -> DetailOut:
    apps: list[Application] = (
        db.query(Application)
        .filter(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            *_between(Application.created_at, fr, to),
        )
        .all()
    )
    aids = [a.id for a in apps]

    status_events: list[ApplicationEvent] = (
        db.query(ApplicationEvent)
        .filter(
            ApplicationEvent.application_id.in_(aids),
            ApplicationEvent.kind == ApplicationEventKind.status_change,
        )
        .all()
        if aids
        else []
    )

    interactions: list[Interaction] = (
        db.query(Interaction)
        .filter(Interaction.application_id.in_(aids))
        .all()
        if aids
        else []
    )

    postings: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    if aids:
        rows = (
            db.query(JobPosting.application_id, JobPosting.company, JobPosting.title)
            .filter(JobPosting.application_id.in_(aids))
            .all()
        )
        for app_id, company, title in rows:
            postings[app_id] = (company, title)

    return DetailOut(
        outcomes=compute_outcomes(apps),
        declines_weekly=compute_declines_weekly(apps, status_events),
        decline_timeline=compute_decline_timeline(apps, status_events, interactions, postings),
        rejection_stage=compute_rejection_stage(apps, status_events, interactions),
        velocity=compute_velocity(apps, status_events, interactions),
        ghost=compute_ghost(apps, status_events, interactions, ghost_days),
        interview=compute_interview(apps, status_events, interactions),
    )
