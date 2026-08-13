from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import (
    Application,
    InteractionChannel,
    InterviewStage,
    JobPosting,
    Interaction,
    User,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarInterview(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    display_id: int
    company: str
    starts_at: datetime
    ends_at: datetime | None
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
