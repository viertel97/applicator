"""Celery task: poll the Outlook "Interviews" calendar and stage events.

Reads each user's refresh token (Fernet-encrypted), mints a Graph access token,
delta-syncs the target calendar, and stages changes as CalendarSuggestions for
user review (see calendar_sync.sync). Nothing becomes a real interview until the
user confirms; only already-confirmed events keep their linked Interaction in
step. Skips cleanly when OAuth is disabled or no token is stored.
"""
from __future__ import annotations

import logging
from datetime import datetime

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


class NoOutlookToken(Exception):
    """User has no stored Outlook refresh token (never connected)."""


class TokenRefreshFailed(Exception):
    """A refresh token exists but Graph declined to mint an access token."""


def _ms_config(s: Settings) -> MSConfig:
    return MSConfig(
        tenant_id=s.ms_tenant_id,
        client_id=s.ms_client_id,
        client_secret=s.ms_client_secret,
        redirect_uri=s.ms_redirect_uri,
    )


def _access_token(db: Session, user: User, settings: Settings) -> str:
    """Mint a Graph access token from the user's stored refresh token.

    Raises NoOutlookToken when nothing is stored, TokenRefreshFailed when the
    refresh is rejected (revoked consent). Rotates the stored refresh token if
    Graph issues a new one.
    """
    if not user.ms_refresh_token_encrypted:
        raise NoOutlookToken()
    refresh = decrypt(user.ms_refresh_token_encrypted, settings.app_secret_key)
    token = acquire_token_by_refresh_token(_ms_config(settings), refresh)
    access = token.get("access_token")
    if not access:
        msg = token.get("error_description") or token.get("error") or "token refresh failed"
        logger.warning(
            "calendar sync: token refresh failed for user %s: %s", user.id, msg
        )
        raise TokenRefreshFailed(str(msg))
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


def _record_health(
    user: User,
    *,
    status: str,
    trigger: str,
    reason: str | None = None,
    counts: dict | None = None,
    error: str | None = None,
) -> None:
    # naive UTC, matching how all datetimes are stored in this codebase
    user.outlook_last_sync_at = datetime.utcnow()
    user.outlook_last_status = status
    user.outlook_last_reason = reason
    user.outlook_last_trigger = trigger
    user.outlook_last_counts = counts
    user.outlook_last_error = error


def sync_user_calendar(
    db: Session,
    user: User,
    settings: Settings,
    *,
    graph: GraphClient | None = None,
    trigger: str = "scheduled",
) -> dict:
    """Sync one user's Outlook calendar. `graph` is injectable for tests.

    Records latest-run health on `user` on every exit path (skip/ok/error).
    """
    if graph is None:
        try:
            access = _access_token(db, user, settings)
        except NoOutlookToken:
            _record_health(user, status="skipped", reason="no_token", trigger=trigger)
            db.commit()
            return {"skipped": "no_token"}
        except TokenRefreshFailed as exc:
            _record_health(
                user, status="error", reason="token_refresh_failed",
                trigger=trigger, error=str(exc),
            )
            db.commit()
            return {"skipped": "token_refresh_failed"}
        graph = GraphClient(access)

    try:
        calendar_id = graph.resolve_calendar_id(settings.outlook_calendar_name)
        if calendar_id is None:
            logger.info(
                "calendar sync: calendar %r not found for user %s",
                settings.outlook_calendar_name, user.id,
            )
            _record_health(user, status="skipped", reason="no_calendar", trigger=trigger)
            db.commit()
            return {"skipped": "no_calendar"}

        state = _get_or_create_state(db, user, calendar_id)
        try:
            events, delta_link = graph.delta_events(calendar_id, state.delta_link)
        except DeltaExpired:
            logger.info(
                "calendar sync: delta link expired for user %s, full re-sync", user.id
            )
            state.delta_link = None
            events, delta_link = graph.delta_events(calendar_id, None)

        stats = sync_calendar_events(db, user, events)
        state.delta_link = delta_link
    except GraphRateLimited as exc:
        db.rollback()
        _record_health(
            user, status="error", reason="rate_limited", trigger=trigger, error=str(exc)
        )
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - record then re-raise for the task
        db.rollback()
        _record_health(
            user, status="error", reason="graph_error",
            trigger=trigger, error=str(exc)[:500],
        )
        db.commit()
        raise

    _record_health(user, status="ok", trigger=trigger, counts=stats)
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
