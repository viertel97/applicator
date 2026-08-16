"""Celery task: poll the Outlook "Interviews" calendar and mirror events.

One-way fan-out. Reads each user's refresh token (Fernet-encrypted), mints a
Graph access token, delta-syncs the target calendar, and projects changes into
Interactions. Skips cleanly when OAuth is disabled or no token is stored.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.ms_oauth import MSConfig, acquire_token_by_refresh_token
from app.calendar_sync.graph import DeltaExpired, GraphClient, GraphRateLimited
from app.calendar_sync.sync import sync_calendar_events
from app.config import Settings, get_settings
from app.crypto import decrypt, encrypt
from app.db.models import CalendarSyncState, User
from app.db.session import get_session_factory
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _ms_config(s: Settings) -> MSConfig:
    return MSConfig(
        tenant_id=s.ms_tenant_id,
        client_id=s.ms_client_id,
        client_secret=s.ms_client_secret,
        redirect_uri=s.ms_redirect_uri,
    )


def _access_token(db: Session, user: User, settings: Settings) -> str | None:
    """Mint a Graph access token from the user's stored refresh token.

    Returns None (and logs) when there is no token or consent was revoked.
    Rotates the stored refresh token if Graph issues a new one.
    """
    if not user.ms_refresh_token_encrypted:
        return None
    refresh = decrypt(user.ms_refresh_token_encrypted, settings.app_secret_key)
    token = acquire_token_by_refresh_token(_ms_config(settings), refresh)
    access = token.get("access_token")
    if not access:
        logger.warning(
            "calendar sync: token refresh failed for user %s: %s",
            user.id,
            token.get("error_description") or token.get("error"),
        )
        return None
    new_refresh = token.get("refresh_token")
    if new_refresh:
        user.ms_refresh_token_encrypted = encrypt(new_refresh, settings.app_secret_key)
    return access


def _get_or_create_state(
    db: Session, user: User, calendar_id: str
) -> CalendarSyncState:
    st = db.execute(
        select(CalendarSyncState).where(
            CalendarSyncState.user_id == user.id,
            CalendarSyncState.calendar_id == calendar_id,
        )
    ).scalar_one_or_none()
    if st is None:
        st = CalendarSyncState(user_id=user.id, calendar_id=calendar_id, delta_link=None)
        db.add(st)
        db.flush()
    return st


def sync_user_calendar(
    db: Session,
    user: User,
    settings: Settings,
    *,
    graph: GraphClient | None = None,
) -> dict:
    """Sync one user's Outlook calendar. `graph` is injectable for tests."""
    if graph is None:
        access = _access_token(db, user, settings)
        if access is None:
            return {"skipped": "no_token"}
        graph = GraphClient(access)

    calendar_id = graph.resolve_calendar_id(settings.outlook_calendar_name)
    if calendar_id is None:
        logger.info(
            "calendar sync: calendar %r not found for user %s",
            settings.outlook_calendar_name,
            user.id,
        )
        return {"skipped": "no_calendar"}

    state = _get_or_create_state(db, user, calendar_id)
    try:
        events, delta_link = graph.delta_events(calendar_id, state.delta_link)
    except DeltaExpired:
        # Stale cursor — reset and do a full re-sync.
        logger.info("calendar sync: delta link expired for user %s, full re-sync", user.id)
        state.delta_link = None
        events, delta_link = graph.delta_events(calendar_id, None)

    stats = sync_calendar_events(db, user, events)
    state.delta_link = delta_link
    db.commit()
    return stats


@celery_app.task(bind=True, name="tasks.sync_outlook_calendar", max_retries=5)
def sync_outlook_calendar_task(self) -> dict:
    settings = get_settings()
    if not settings.oauth_enabled:
        return {"skipped": "oauth_disabled"}

    db = get_session_factory()()
    try:
        users = db.execute(
            select(User).where(User.ms_refresh_token_encrypted.is_not(None))
        ).scalars().all()
        results: dict = {}
        for user in users:
            try:
                results[str(user.id)] = sync_user_calendar(db, user, settings)
            except GraphRateLimited as exc:
                # Respect Retry-After; sync is idempotent so a retry is safe.
                raise self.retry(countdown=exc.retry_after) from exc
        return results
    finally:
        db.close()
