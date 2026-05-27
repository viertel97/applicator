import uuid
from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import (
    Application, ApplicationStatus, DiscardReason, Interaction,
    InteractionDirection, Interview, User,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])


class FunnelStage(BaseModel):
    stage: str
    count: int


class ChannelRate(BaseModel):
    channel: str
    outgoing: int
    responses: int
    rate: float


class DiscardBreakdown(BaseModel):
    slug: str
    label: str
    count: int


class WeeklyVolume(BaseModel):
    week: str
    applied: int
    discarded: int
    responses: int


class FunnelOut(BaseModel):
    totals: dict
    funnel: list[FunnelStage]
    response_rate_by_channel: list[ChannelRate]
    avg_time_to_reply_hours: dict
    discard_breakdown: list[DiscardBreakdown]
    weekly_volume: list[WeeklyVolume]


def _between(col, fr: datetime | None, to: datetime | None):
    out = []
    if fr is not None:
        out.append(col >= fr)
    if to is not None:
        out.append(col <= to)
    return out


@router.get("/funnel", response_model=FunnelOut)
def funnel(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    fr: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
):
    base = db.query(Application).filter(
        Application.user_id == user.id,
        Application.deleted_at.is_(None),
        *_between(Application.created_at, fr, to),
    )
    apps = base.all()
    aids = [a.id for a in apps]

    total = len(apps)
    by_status: dict[str, int] = defaultdict(int)
    for a in apps:
        by_status[a.status.value] += 1

    # all in interactions for these apps
    in_rows: list[Interaction] = (
        db.query(Interaction)
          .filter(Interaction.application_id.in_(aids),
                  Interaction.direction == InteractionDirection.in_)
          .all() if aids else []
    )
    responded_app_ids = {it.application_id for it in in_rows}

    interview_app_ids = {
        i.application_id for i in (
            db.query(Interview).filter(Interview.application_id.in_(aids)).all()
            if aids else []
        )
    }

    funnel_stages = [
        FunnelStage(stage="created", count=total),
        FunnelStage(stage="applied",
                    count=sum(1 for a in apps if a.status != ApplicationStatus.draft)),
        FunnelStage(stage="responded", count=len(responded_app_ids)),
        FunnelStage(stage="interview", count=len(interview_app_ids)),
        FunnelStage(stage="offer", count=by_status.get("offer", 0)),
        FunnelStage(stage="accepted", count=by_status.get("accepted", 0)),
    ]

    # response rate per channel — same-channel + ordering rule
    out_rows: list[Interaction] = (
        db.query(Interaction)
          .filter(Interaction.application_id.in_(aids),
                  Interaction.direction == InteractionDirection.out)
          .all() if aids else []
    )
    earliest_out: dict[tuple[uuid.UUID, str], datetime] = {}
    for it in out_rows:
        key = (it.application_id, it.channel.value)
        if key not in earliest_out or it.occurred_at < earliest_out[key]:
            earliest_out[key] = it.occurred_at

    out_apps_per_channel: dict[str, set[uuid.UUID]] = defaultdict(set)
    for (aid, ch), _ in earliest_out.items():
        out_apps_per_channel[ch].add(aid)

    response_apps_per_channel: dict[str, set[uuid.UUID]] = defaultdict(set)
    reply_deltas: dict[str, list[float]] = defaultdict(list)
    for it in in_rows:
        ch = it.channel.value
        key = (it.application_id, ch)
        out_at = earliest_out.get(key)
        if out_at and it.occurred_at > out_at:
            if it.application_id not in response_apps_per_channel[ch]:
                response_apps_per_channel[ch].add(it.application_id)
                reply_deltas[ch].append(
                    (it.occurred_at - out_at).total_seconds() / 3600.0
                )

    channel_rates: list[ChannelRate] = []
    for ch in sorted({c for _, c in earliest_out.keys()}):
        out_count = len(out_apps_per_channel[ch])
        in_count = len(response_apps_per_channel[ch])
        rate = (in_count / out_count) if out_count else 0.0
        channel_rates.append(ChannelRate(
            channel=ch, outgoing=out_count, responses=in_count, rate=rate,
        ))

    avg_reply = {
        ch: round(sum(v) / len(v), 1) for ch, v in reply_deltas.items() if v
    }

    # discard breakdown
    discard_rows = (
        db.query(DiscardReason.slug, DiscardReason.label, func.count(Application.id))
          .join(Application, Application.discard_reason_id == DiscardReason.id)
          .filter(Application.user_id == user.id,
                  Application.deleted_at.is_(None))
          .group_by(DiscardReason.slug, DiscardReason.label)
          .order_by(func.count(Application.id).desc())
          .all()
    )
    discard_breakdown = [
        DiscardBreakdown(slug=s, label=l, count=c) for s, l, c in discard_rows
    ]

    # weekly volume: ISO week, applied/discarded/responses
    weekly: dict[str, dict[str, int]] = defaultdict(lambda: {
        "applied": 0, "discarded": 0, "responses": 0,
    })
    for a in apps:
        wk = a.created_at.strftime("%G-W%V")
        if a.status != ApplicationStatus.draft:
            weekly[wk]["applied"] += 1
        if a.status == ApplicationStatus.discarded:
            weekly[wk]["discarded"] += 1
    for it in in_rows:
        wk = it.occurred_at.strftime("%G-W%V")
        weekly[wk]["responses"] += 1
    weekly_volume = [
        WeeklyVolume(week=w, **vals) for w, vals in sorted(weekly.items())
    ]

    totals = {
        "applications": total,
        "applied": sum(1 for a in apps if a.status != ApplicationStatus.draft),
        "discarded": by_status.get("discarded", 0),
        "active": sum(
            1 for a in apps
            if a.status not in (
                ApplicationStatus.discarded, ApplicationStatus.rejected,
                ApplicationStatus.withdrawn, ApplicationStatus.accepted,
            )
        ),
    }

    return FunnelOut(
        totals=totals,
        funnel=funnel_stages,
        response_rate_by_channel=channel_rates,
        avg_time_to_reply_hours=avg_reply,
        discard_breakdown=discard_breakdown,
        weekly_volume=weekly_volume,
    )
