import uuid
from typing import Annotated

from celery import chain
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import db_dep, settings_dep
from app.config import Settings
from app.db.models import Application
from app.pipeline import url_hash
from app.tasks.pipeline import crawl_task, extract_task, notify_task

router = APIRouter(prefix="/api/bot", tags=["bot"])


class BotCreateApplication(BaseModel):
    url: HttpUrl
    chat_id: int


def _bot_auth(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(settings_dep),
) -> None:
    expected = f"Bearer {settings.bot_api_key}"
    if not settings.bot_api_key or authorization != expected:
        raise HTTPException(401, "unauthorized")


def _start_bot_chain(app_id: uuid.UUID, chat_id: int) -> None:
    chain(
        crawl_task.s(str(app_id)),
        extract_task.s(),
        notify_task.s(chat_id),
    ).apply_async()


@router.post("/applications")
def bot_create_application(
    body: BotCreateApplication,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    _auth: Annotated[None, Depends(_bot_auth)],
):
    if not settings.app_user_id:
        raise HTTPException(500, "APP_USER_ID not configured")
    try:
        user_id = uuid.UUID(settings.app_user_id)
    except ValueError:
        raise HTTPException(500, "APP_USER_ID is not a valid UUID")
    h = url_hash(str(body.url))
    existing = db.query(Application).filter_by(user_id=user_id, url_hash=h).first()
    if existing:
        raise HTTPException(409, f"application already exists: {existing.id}")
    app_row = Application(user_id=user_id, url=str(body.url), url_hash=h)
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    _start_bot_chain(app_row.id, body.chat_id)
    return {"app_id": str(app_row.id), "url": str(body.url)}
