from __future__ import annotations

import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _ensure(db: Session, user: User, attr: str) -> str:
    current = getattr(user, attr)
    if current:
        return current
    setattr(user, attr, new_token())
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.refresh(user)
    return getattr(user, attr)


def ensure_ingest_token(db: Session, user: User) -> str:
    return _ensure(db, user, "ingest_token")


def ensure_calendar_token(db: Session, user: User) -> str:
    return _ensure(db, user, "calendar_token")


def regenerate(db: Session, user: User, kind: str) -> None:
    if kind == "ingest":
        user.ingest_token = new_token()
    elif kind == "calendar":
        user.calendar_token = new_token()
    else:
        raise ValueError(f"unknown token kind: {kind}")
    db.commit()
