import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.db.models import Session as SessionRow

SESSION_TTL_DAYS = 30


def create_session(db: DBSession, user_id) -> str:
    sid = secrets.token_urlsafe(32)
    row = SessionRow(
        id=sid,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(row)
    db.commit()
    return sid


def lookup_session(db: DBSession, sid: str) -> SessionRow | None:
    row = db.get(SessionRow, sid)
    if row is None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None
    return row


def delete_session(db: DBSession, sid: str) -> None:
    row = db.get(SessionRow, sid)
    if row is not None:
        db.delete(row)
        db.commit()
