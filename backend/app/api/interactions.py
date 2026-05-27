import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import (
    Application,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
    InteractionSentiment,
    User,
)

router = APIRouter(prefix="/api", tags=["interactions"])


class InteractionIn(BaseModel):
    occurred_at: datetime | None = None
    direction: InteractionDirection
    channel: InteractionChannel
    subject: str | None = None
    body: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None
    sentiment: InteractionSentiment | None = None


class InteractionPatch(BaseModel):
    occurred_at: datetime | None = None
    direction: InteractionDirection | None = None
    channel: InteractionChannel | None = None
    subject: str | None = None
    body: str | None = None
    contact_name: str | None = None
    contact_handle: str | None = None
    sentiment: InteractionSentiment | None = None


class InteractionOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    occurred_at: datetime
    direction: InteractionDirection
    channel: InteractionChannel
    subject: str | None
    body: str | None
    contact_name: str | None
    contact_handle: str | None
    sentiment: InteractionSentiment | None
    created_from: InteractionCreatedFrom
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SuggestDiscard(BaseModel):
    reason_slug: str
    interaction_id: uuid.UUID


class CreateInteractionOut(BaseModel):
    interaction: InteractionOut
    suggest_discard: SuggestDiscard | None = None


def _own_app(db: Session, user: User, aid: uuid.UUID) -> Application:
    a = db.get(Application, aid)
    if not a or a.user_id != user.id or a.deleted_at is not None:
        raise HTTPException(404, "not found")
    return a


def _own_interaction(db: Session, user: User, iid: uuid.UUID) -> Interaction:
    it = db.get(Interaction, iid)
    if not it:
        raise HTTPException(404, "not found")
    _own_app(db, user, it.application_id)
    return it


@router.get("/applications/{aid}/interactions", response_model=list[InteractionOut])
def list_interactions(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    return (
        db.query(Interaction)
        .filter_by(application_id=aid)
        .order_by(Interaction.occurred_at.desc())
        .all()
    )


@router.post("/applications/{aid}/interactions", response_model=CreateInteractionOut)
def create_interaction(
    aid: uuid.UUID,
    body: InteractionIn,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    _own_app(db, user, aid)
    it = Interaction(
        application_id=aid,
        occurred_at=body.occurred_at or datetime.now(timezone.utc),
        direction=body.direction,
        channel=body.channel,
        subject=body.subject,
        body=body.body,
        contact_name=body.contact_name,
        contact_handle=body.contact_handle,
        sentiment=body.sentiment,
        created_from=InteractionCreatedFrom.manual,
    )
    db.add(it)
    db.commit()
    db.refresh(it)
    suggest = None
    if (
        body.direction == InteractionDirection.in_
        and body.sentiment == InteractionSentiment.rejection
    ):
        suggest = SuggestDiscard(reason_slug="rejected", interaction_id=it.id)
    return CreateInteractionOut(
        interaction=InteractionOut.model_validate(it),
        suggest_discard=suggest,
    )


@router.patch("/interactions/{iid}", response_model=InteractionOut)
def patch_interaction(
    iid: uuid.UUID,
    body: InteractionPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    it = _own_interaction(db, user, iid)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(it, field, val)
    db.commit()
    db.refresh(it)
    return it


@router.delete("/interactions/{iid}", status_code=204)
def delete_interaction(
    iid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    it = _own_interaction(db, user, iid)
    db.delete(it)
    db.commit()
    return None
