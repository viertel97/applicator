from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.session import lookup_session
from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db


def settings_dep() -> Settings:
    return get_settings()


def db_dep() -> Iterator[Session]:
    yield from get_db()


def current_user(
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    session_cookie: str | None = Cookie(default=None, alias="applicator_session"),
) -> User:
    if not session_cookie:
        raise HTTPException(401, "not authenticated")
    row = lookup_session(db, session_cookie)
    if row is None:
        raise HTTPException(401, "session invalid or expired")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "user gone")
    return user
