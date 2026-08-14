from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.api.serializers import UtcDateTime
from app.calendar_feed.ics import IcsEvent, render_calendar
from app.db.models import (
    Application,
    InteractionChannel,
    InterviewStage,
    JobPosting,
    Interaction,
    User,
)
from app.services.tokens import ensure_calendar_token, ensure_ingest_token, regenerate

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarInterview(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    display_id: int
    company: str
    starts_at: UtcDateTime
    ends_at: UtcDateTime | None
    location: str | None
    interview_stage: InterviewStage | None
    needs_review: bool


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _company(jp: JobPosting | None, url: str) -> str:
    if jp and jp.company:
        return jp.company
    host = urlparse(url).netloc
    return host or "Unknown"


@router.get("/interviews", response_model=list[CalendarInterview])
def list_interviews(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
) -> list[CalendarInterview]:
    stmt = (
        select(Interaction, Application, JobPosting)
        .join(Application, Interaction.application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            Interaction.channel == InteractionChannel.interview,
        )
    )
    if from_ is not None:
        stmt = stmt.where(Interaction.occurred_at >= _naive(from_))
    if to is not None:
        stmt = stmt.where(Interaction.occurred_at <= _naive(to))
    stmt = stmt.order_by(Interaction.occurred_at.asc())

    out: list[CalendarInterview] = []
    for it, app, jp in db.execute(stmt).all():
        out.append(
            CalendarInterview(
                id=it.id,
                application_id=app.id,
                display_id=app.display_id,
                company=_company(jp, app.url),
                starts_at=it.occurred_at,
                ends_at=it.ends_at,
                location=it.location,
                interview_stage=it.interview_stage,
                needs_review=it.needs_review,
            )
        )
    return out


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/tokens")
def get_tokens(
    request: Request,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    ingest = ensure_ingest_token(db, user)
    cal = ensure_calendar_token(db, user)
    base = _base_url(request)
    return {
        "ingest_url": f"{base}/api/webhooks/inbound-email/{ingest}",
        "calendar_url": f"{base}/api/calendar/{cal}.ics",
    }


@router.post("/tokens/regenerate")
def regenerate_token(
    kind: str,
    request: Request,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    if kind not in ("ingest", "calendar"):
        raise HTTPException(400, "kind must be ingest or calendar")
    regenerate(db, user, kind)
    return get_tokens(request, db, user)


@router.get("/review-count")
def review_count(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    n = db.execute(
        select(func.count(Interaction.id))
        .join(Application, Interaction.application_id == Application.id)
        .where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            Interaction.channel == InteractionChannel.interview,
            Interaction.needs_review.is_(True),
        )
    ).scalar_one()
    return {"count": int(n)}


def _lookup_by_calendar_token(db: Session, token: str) -> User:
    row = db.execute(select(User).where(User.calendar_token == token)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.get("/{token}.ics")
def ics_feed(
    token: str,
    request: Request,
    db: Annotated[Session, Depends(db_dep)],
) -> Response:
    user = _lookup_by_calendar_token(db, token)
    stmt = (
        select(Interaction, Application, JobPosting)
        .join(Application, Interaction.application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
            Interaction.channel == InteractionChannel.interview,
            Interaction.needs_review.is_(False),
        )
        .order_by(Interaction.occurred_at.asc())
    )
    base = _base_url(request)
    events: list[IcsEvent] = []
    for it, app, jp in db.execute(stmt).all():
        company = _company(jp, app.url)
        stage = it.interview_stage.value if it.interview_stage else "interview"
        deep = f"{base}/applications/{app.id}"
        events.append(
            IcsEvent(
                uid=str(it.id),
                summary=f"{company} · {stage}",
                starts_at=it.occurred_at,
                ends_at=it.ends_at,
                location=it.location,
                description="\n".join(filter(None, [it.subject, deep])),
                updated_at=it.updated_at,
            )
        )
    body = render_calendar(events)
    return Response(content=body, media_type="text/calendar; charset=utf-8")
