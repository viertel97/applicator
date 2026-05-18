import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Application, ApplicationStatus
from app.db.session import get_session_factory
from app.llm.groq import GroqClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_OFFLINE_STATUSES = frozenset((404, 410))
_OFFLINE_KEYWORDS = [
    "nicht mehr verfügbar",
    "position filled",
    "job no longer available",
    "diese stelle wurde",
    "anzeige abgelaufen",
    "no longer accepting",
    "position has been filled",
]
_SKIP_WITHIN = timedelta(hours=4)
_RATE_LIMIT_SLEEP = 1.0

FetchFn = Callable[[str], tuple[int, str]]


def _strip_tags(html: str) -> str:
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


def _default_fetch(url: str) -> tuple[int, str]:
    with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": _UA}) as c:
        r = c.get(url)
    return r.status_code, _strip_tags(r.text)


def _heuristic(status_code: int, text: str) -> bool | None:
    """Returns True=online, False=offline, None=inconclusive."""
    if status_code in _OFFLINE_STATUSES:
        return False
    if status_code == 200:
        lower = text.lower()
        return not any(kw in lower for kw in _OFFLINE_KEYWORDS)
    return None


def _llm_check(text: str, llm) -> bool | None:
    try:
        resp = llm.complete(
            [
                {"role": "system", "content": "Answer only 'yes' or 'no'."},
                {
                    "role": "user",
                    "content": (
                        f"Is this page still an active job posting? Answer yes or no.\n\n{text[:3000]}"
                    ),
                },
            ],
            temperature=0.0,
        )
        return resp.strip().lower().startswith("y")
    except Exception as exc:
        logger.warning("LLM online check failed: %s", exc)
        return None


def _check_one(url: str, llm, fetch_fn: FetchFn | None = None) -> bool | None:
    _fetch = fetch_fn or _default_fetch
    try:
        status, text = _fetch(url)
    except Exception as exc:
        logger.warning("fetch error for %s: %s", url, exc)
        return None
    result = _heuristic(status, text)
    if result is None:
        result = _llm_check(text, llm)
    return result


@contextmanager
def _db() -> Iterator[Session]:
    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


@celery_app.task(name="tasks.check_postings")
def check_postings_task() -> dict:
    settings = get_settings()
    llm = GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )
    skip_after = datetime.now(timezone.utc) - _SKIP_WITHIN

    with _db() as db:
        apps = (
            db.query(Application)
            .filter(
                Application.status.notin_(
                    [ApplicationStatus.withdrawn, ApplicationStatus.rejected]
                )
            )
            .all()
        )

    checked = skipped = 0
    for i, app in enumerate(apps):
        checked_at = app.posting_checked_at
        if checked_at is not None:
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if checked_at > skip_after:
                skipped += 1
                continue

        online = _check_one(app.url, llm)

        if online is not None:
            with _db() as db:
                fresh = db.get(Application, app.id)
                if fresh is not None:
                    fresh.posting_online = online
                    fresh.posting_checked_at = datetime.now(timezone.utc)
                    db.commit()

        checked += 1
        if i < len(apps) - 1:
            time.sleep(_RATE_LIMIT_SLEEP)

    return {"checked": checked, "skipped": skipped}
