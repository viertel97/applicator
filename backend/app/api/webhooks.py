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
    WebhookRequest,
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
    # Mutable holder — one WebhookRequest row is written from `finally` on
    # EVERY path (success, ignored, and re-raised HTTPExceptions).
    rec: dict = {
        "ingest_token": ingest_token,
        "source_ip": request.client.host if request.client else None,
        "headers": dict(request.headers),
        "raw_body": None,
        "user_id": None,
        "status": "ignored",
        "reason": None,
        "matched_application_id": None,
    }
    try:
        user = _lookup_user(db, ingest_token)  # raises HTTPException(404)
        rec["user_id"] = user.id

        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > _MAX_BODY:
            # Body not read on this pre-check path — raw_body stays null.
            raise HTTPException(413, "payload too large")
        raw = await request.body()
        rec["raw_body"] = raw.decode("utf-8", "replace")
        if len(raw) > _MAX_BODY:
            raise HTTPException(413, "payload too large")

        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            rec["reason"] = "unparseable"
            return {"status": "ignored", "reason": "unparseable"}
        email = InboundEmail.normalize(payload)

        llm = _webhook_llm()
        if llm is None:
            rec["reason"] = "llm unavailable"
            return {"status": "ignored", "reason": "llm unavailable"}
        try:
            extracted = extract_interview(email.subject, email.body_text, llm)
        except Exception:
            rec["reason"] = "extraction failed"
            return {"status": "ignored", "reason": "extraction failed"}

        apps = db.execute(
            select(Application, JobPosting)
            .outerjoin(JobPosting, JobPosting.application_id == Application.id)
            .where(Application.user_id == user.id, Application.deleted_at.is_(None))
        ).all()
        if not apps:
            rec["reason"] = "no applications"
            return {"status": "ignored", "reason": "no applications"}

        candidates = [
            Candidate(application_id=str(a.id), company=(jp.company if jp else None), url=a.url)
            for a, jp in apps
        ]
        app_id, _score = match_application(
            sender=email.from_, subject=email.subject, body=email.body_text,
            candidates=candidates,
        )
        if app_id is None:
            rec["reason"] = "no match"
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
        rec["status"] = "created"
        rec["matched_application_id"] = _uuid.UUID(app_id)
        # NOTE: no db.commit() here — the `finally` commits the interaction,
        # event, and WebhookRequest together.
        return {"status": "created", "needs_review": True}
    except HTTPException as exc:
        if exc.status_code == 404:
            rec["status"] = "not_found"
            rec["reason"] = "unknown token"
        elif exc.status_code == 413:
            rec["status"] = "rejected"
            rec["reason"] = "payload too large"
        raise
    except Exception as exc:
        # Unexpected failure — record it in the audit row instead of a silent
        # "ignored", and re-raise so the 500 still surfaces to the caller.
        rec["status"] = "error"
        rec["reason"] = type(exc).__name__
        raise
    finally:
        # The audit row must persist even if the main work poisoned the
        # transaction. Try the combined commit first (preserves happy-path
        # atomicity of interaction+event+audit); if that fails, roll back and
        # write the audit row alone. Never raise from finally — that would
        # mask the real exception being propagated.
        try:
            db.add(WebhookRequest(**rec))
            db.commit()
        except Exception:
            db.rollback()
            try:
                db.add(WebhookRequest(**rec))
                db.commit()
            except Exception:
                pass
