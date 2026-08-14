from __future__ import annotations

import json
import uuid as _uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import db_dep
from app.config import get_settings
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationEventKind,
    Interaction,
    InteractionChannel,
    InteractionCreatedFrom,
    InteractionDirection,
    InterviewStage,
    JobPosting,
    User,
)
from app.email_ingest.interview_extract import extract_interview
from app.email_ingest.interview_match import Candidate, match_application

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_MAX_BODY = 512 * 1024  # 512 KB


class InboundEmail(BaseModel):
    from_: str = ""
    subject: str = ""
    body_text: str = ""

    model_config = {"populate_by_name": True}

    @classmethod
    def normalize(cls, payload: dict) -> "InboundEmail":
        return cls(
            from_=payload.get("from") or payload.get("sender") or "",
            subject=payload.get("subject") or "",
            body_text=payload.get("body_text") or payload.get("text")
            or payload.get("body") or "",
        )


def _webhook_llm():
    from app.llm.groq import GroqClient
    s = get_settings()
    if not s.llm_api_key:
        return None
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)


def _lookup_user(db: Session, token: str) -> User:
    row = db.execute(select(User).where(User.ingest_token == token)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not found")
    return row


@router.post("/inbound-email/{ingest_token}", status_code=202)
async def inbound_email(
    ingest_token: str, request: Request, db: Annotated[Session, Depends(db_dep)],
):
    user = _lookup_user(db, ingest_token)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_BODY:
        raise HTTPException(413, "payload too large")
    raw = await request.body()
    if len(raw) > _MAX_BODY:
        raise HTTPException(413, "payload too large")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"status": "ignored", "reason": "unparseable"}
    email = InboundEmail.normalize(payload)

    llm = _webhook_llm()
    if llm is None:
        return {"status": "ignored", "reason": "llm unavailable"}
    try:
        extracted = extract_interview(email.subject, email.body_text, llm)
    except Exception:
        return {"status": "ignored", "reason": "extraction failed"}

    apps = db.execute(
        select(Application, JobPosting)
        .outerjoin(JobPosting, JobPosting.application_id == Application.id)
        .where(Application.user_id == user.id, Application.deleted_at.is_(None))
    ).all()
    if not apps:
        return {"status": "ignored", "reason": "no applications"}

    candidates = [
        Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
        for a, jp in apps
    ]
    app_id, _score = match_application(
        sender=email.from_, subject=email.subject, body=email.body_text, candidates=candidates,
    )
    if app_id is None:
        return {"status": "ignored", "reason": "no match"}
    stage = None
    if extracted.interview_stage:
        stage = InterviewStage(extracted.interview_stage)

    kwargs = dict(
        application_id=_uuid.UUID(app_id),
        ends_at=extracted.ends_at,
        direction=InteractionDirection.in_,
        channel=InteractionChannel.interview,
        interview_stage=stage,
        location=extracted.location,
        contact_name=extracted.contact_name,
        contact_handle=extracted.contact_handle,
        subject=email.subject,
        body=email.body_text,
        needs_review=True,
        created_from=InteractionCreatedFrom.email_webhook,
    )
    if extracted.starts_at is not None:
        kwargs["occurred_at"] = extracted.starts_at
    it = Interaction(**kwargs)
    db.add(it)
    db.add(ApplicationEvent(
        application_id=_uuid.UUID(app_id),
        kind=ApplicationEventKind.interview_scheduled,
    ))
    db.commit()
    return {"status": "created", "needs_review": True}
