import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    JobPosting,
    User,
)
from app.email_ingest.parser import parse_eml

router = APIRouter(prefix="/api", tags=["interactions"])

MAX_EML_BYTES = 10 * 1024 * 1024  # 10 MB


def _eml_llm():
    from app.config import get_settings
    from app.llm.groq import GroqClient

    s = get_settings()
    if not s.llm_api_key:
        return None
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)


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


class ImportEmlOut(BaseModel):
    interactions: list[InteractionOut]
    count: int
    used_llm: bool


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


def _message_to_interaction(aid, msg, user, top_dt, index, job_contact):
    sender = (msg.sender_email or "").lower()
    is_out = bool(sender and user.email and sender == user.email.lower())
    direction = InteractionDirection.out if is_out else InteractionDirection.in_

    if direction == InteractionDirection.in_:
        cname, chandle = msg.sender_name, msg.sender_email
    else:
        chandle = msg.recipients[0] if msg.recipients else None
        cname = None

    if not (cname or chandle) and job_contact:
        cname = job_contact.get("name")
        chandle = job_contact.get("email")

    occurred = msg.occurred_at or (top_dt - timedelta(seconds=index))

    return Interaction(
        application_id=aid,
        occurred_at=occurred,
        direction=direction,
        channel=InteractionChannel.mail,
        subject=msg.subject,
        body=msg.body or None,
        contact_name=cname,
        contact_handle=chandle,
        sentiment=None,
        created_from=InteractionCreatedFrom.eml_import,
    )


@router.post(
    "/applications/{aid}/interactions/import-eml",
    response_model=ImportEmlOut,
)
async def import_eml(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    _own_app(db, user, aid)
    if not (file.filename or "").lower().endswith(".eml"):
        raise HTTPException(400, "only .eml files are accepted")
    if file.size is not None and file.size > MAX_EML_BYTES:
        raise HTTPException(413, "file too large")
    raw = await file.read()
    if len(raw) > MAX_EML_BYTES:
        raise HTTPException(413, "file too large")

    thread = parse_eml(raw, llm=_eml_llm())
    if not thread.messages:
        raise HTTPException(422, "could not parse email")

    job = db.query(JobPosting).filter_by(application_id=aid).first()
    job_contact = job.contact if job and isinstance(job.contact, dict) else None
    top_dt = thread.messages[0].occurred_at or datetime.now(timezone.utc)

    rows = [
        _message_to_interaction(aid, m, user, top_dt, i, job_contact)
        for i, m in enumerate(thread.messages)
    ]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)

    return ImportEmlOut(
        interactions=[InteractionOut.model_validate(r) for r in rows],
        count=len(rows),
        used_llm=thread.used_llm,
    )
