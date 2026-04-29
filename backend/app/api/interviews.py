import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Application, Interview, InterviewKind, InterviewOutcome, User

router = APIRouter(prefix="/api", tags=["interviews"])


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    kind: InterviewKind
    notes: str | None = None


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    kind: InterviewKind | None = None
    notes: str | None = None
    outcome: InterviewOutcome | None = None


class InterviewOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_at: datetime
    kind: InterviewKind
    notes: str | None
    outcome: InterviewOutcome

    model_config = {"from_attributes": True}


def _own_app(db: Session, user: User, aid: uuid.UUID) -> Application:
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    return app_row


@router.get("/applications/{aid}/interviews", response_model=list[InterviewOut])
def list_interviews(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    return (
        db.query(Interview)
        .filter_by(application_id=aid)
        .order_by(Interview.scheduled_at.asc())
        .all()
    )


@router.post("/applications/{aid}/interviews", response_model=InterviewOut)
def create_interview(
    aid: uuid.UUID,
    body: InterviewCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    iv = Interview(
        application_id=aid,
        scheduled_at=body.scheduled_at,
        kind=body.kind,
        notes=body.notes,
    )
    db.add(iv)
    db.commit()
    db.refresh(iv)
    return iv


@router.patch("/interviews/{iid}", response_model=InterviewOut)
def update_interview(
    iid: uuid.UUID,
    body: InterviewUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    iv = db.get(Interview, iid)
    if not iv:
        raise HTTPException(404, "not found")
    _own_app(db, user, iv.application_id)
    if body.scheduled_at is not None:
        iv.scheduled_at = body.scheduled_at
    if body.kind is not None:
        iv.kind = body.kind
    if body.notes is not None:
        iv.notes = body.notes
    if body.outcome is not None:
        iv.outcome = body.outcome
    db.commit()
    db.refresh(iv)
    return iv


@router.delete("/interviews/{iid}")
def delete_interview(
    iid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    iv = db.get(Interview, iid)
    if not iv:
        raise HTTPException(404, "not found")
    _own_app(db, user, iv.application_id)
    db.delete(iv)
    db.commit()
    return {"ok": True}
