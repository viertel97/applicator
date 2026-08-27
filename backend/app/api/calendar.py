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
    ApplicationEvent,
    ApplicationEventKind,
    CalendarSuggestion,
    CalendarSuggestionStatus,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
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


class SuggestedApp(BaseModel):
    id: uuid.UUID
    display_id: int
    company: str


class CalendarSuggestionOut(BaseModel):
    id: uuid.UUID
    external_id: str
    subject: str | None
    starts_at: UtcDateTime
    ends_at: UtcDateTime | None
    location: str | None
    organizer_email: str | None
    match_score: float | None
    suggested_application: SuggestedApp | None


class ConfirmSuggestionIn(BaseModel):
    application_id: uuid.UUID | None = None


def _owned_suggestion(db: Session, sid: uuid.UUID, user: User) -> CalendarSuggestion:
    s = db.execute(
        select(CalendarSuggestion).where(
            CalendarSuggestion.id == sid,
            CalendarSuggestion.user_id == user.id,
        )
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "suggestion not found")
    return s


@router.get("/suggestions", response_model=list[CalendarSuggestionOut])
def list_calendar_suggestions(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> list[CalendarSuggestionOut]:
    rows = db.execute(
        select(CalendarSuggestion, Application, JobPosting)
        .outerjoin(Application, CalendarSuggestion.suggested_application_id == Application.id)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(
            CalendarSuggestion.user_id == user.id,
            CalendarSuggestion.status == CalendarSuggestionStatus.pending,
        )
        .order_by(CalendarSuggestion.starts_at.asc())
    ).all()
    out: list[CalendarSuggestionOut] = []
    for s, app, jp in rows:
        suggested = None
        if app is not None:
            suggested = SuggestedApp(
                id=app.id, display_id=app.display_id, company=_company(jp, app.url)
            )
        out.append(
            CalendarSuggestionOut(
                id=s.id,
                external_id=s.external_id,
                subject=s.subject,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                location=s.location,
                organizer_email=s.organizer_email,
                match_score=s.match_score,
                suggested_application=suggested,
            )
        )
    return out


@router.post("/suggestions/{sid}/confirm")
def confirm_calendar_suggestion(
    sid: uuid.UUID,
    payload: ConfirmSuggestionIn,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    s = _owned_suggestion(db, sid, user)
    if s.status != CalendarSuggestionStatus.pending:
        raise HTTPException(409, "suggestion already resolved")

    app_id = payload.application_id or s.suggested_application_id
    if app_id is None:
        raise HTTPException(400, "no application to link; pick one to confirm")
    app_row = db.execute(
        select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if app_row is None:
        raise HTTPException(400, "application not found")

    it = Interaction(
        application_id=app_row.id,
        occurred_at=s.starts_at,
        ends_at=s.ends_at,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        location=s.location,
        subject=s.subject,
        body=s.body,
        needs_review=False,
        created_from=InteractionCreatedFrom.graph_sync,
        external_source=s.external_source,
        external_id=s.external_id,
    )
    db.add(it)
    db.flush()
    db.add(
        ApplicationEvent(
            application_id=app_row.id,
            kind=ApplicationEventKind.interview_scheduled,
            interaction_id=it.id,
        )
    )
    s.status = CalendarSuggestionStatus.confirmed
    s.interaction_id = it.id
    db.commit()
    return {"ok": True, "interaction_id": str(it.id)}


@router.post("/suggestions/{sid}/dismiss")
def dismiss_calendar_suggestion(
    sid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
) -> dict:
    s = _owned_suggestion(db, sid, user)
    if s.status == CalendarSuggestionStatus.pending:
        s.status = CalendarSuggestionStatus.dismissed
        db.commit()
    return {"ok": True}


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
                description="\n\n".join(filter(None, [it.subject, it.body, deep])),
                updated_at=it.updated_at,
            )
        )
    body = render_calendar(events)
    return Response(content=body, media_type="text/calendar; charset=utf-8")
