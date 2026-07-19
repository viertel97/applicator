import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator
from urllib.parse import urlparse

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
_OFFLINE_STATUSES = frozenset((403, 404, 410))
_OFFLINE_KEYWORDS = [
    "nicht mehr verfügbar",
    "position filled",
    "job no longer available",
    "diese stelle wurde",
    "anzeige abgelaufen",
    "no longer accepting",
    "position has been filled",
    "stellenanzeige konnte nicht gefunden werden",
    "keine stellenanzeige gefunden",
    "bereits besetzt",
]
# Single-segment paths that indicate a redirect to a listing/landing page
# rather than the original posting.
_HOMEPAGE_SEGMENTS = frozenset(
    (
        "jobs",
        "job",
        "karriere",
        "career",
        "careers",
        "stellenangebote",
        "stellenanzeigen",
        "stellen",
        "jobboerse",
        "jobsuche",
    )
)
_SKIP_WITHIN = timedelta(hours=4)
_RATE_LIMIT_SLEEP = 1.0

# (status_code, stripped_text, final_url_after_redirects)
FetchFn = Callable[[str], tuple[int, str, str]]

# (online: True/False/None, reason: str | None)
CheckResult = tuple[bool | None, str | None]


def _strip_tags(html: str) -> str:
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    return re.sub(r"\s+", " ", no_tags).strip()


def _default_fetch(url: str) -> tuple[int, str, str]:
    with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": _UA}) as c:
        r = c.get(url)
    return r.status_code, _strip_tags(r.text), str(r.url)


def _redirect_reason(original_url: str, final_url: str) -> str | None:
    """Flag a redirect that landed off-host or on a bare/landing path.

    Returns `redirect_offhost`, `redirect_root`, or None when the final URL
    still looks like a specific posting (same host, deep path)."""
    o = urlparse(original_url)
    f = urlparse(final_url)
    if f.netloc and o.netloc and f.netloc.lower() != o.netloc.lower():
        return "redirect_offhost"
    segments = [s for s in f.path.split("/") if s]
    if not segments:
        return "redirect_root"
    if len(segments) == 1 and segments[0].lower() in _HOMEPAGE_SEGMENTS:
        return "redirect_root"
    return None


def _heuristic(
    status_code: int, text: str, final_url: str, original_url: str
) -> CheckResult:
    """Returns (online, reason). online True=online, False=offline, None=inconclusive."""
    if status_code in _OFFLINE_STATUSES:
        return False, f"http_{status_code}"
    if status_code == 200:
        redirect = _redirect_reason(original_url, final_url)
        if redirect is not None:
            return False, redirect
        lower = text.lower()
        for kw in _OFFLINE_KEYWORDS:
            if kw in lower:
                return False, f"keyword:{kw}"
        return True, None
    return None, None


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


def _check_one(url: str, llm, fetch_fn: FetchFn | None = None) -> CheckResult:
    _fetch = fetch_fn or _default_fetch
    try:
        status, text, final_url = _fetch(url)
    except Exception as exc:
        logger.warning("fetch error for %s: %s", url, exc)
        return None, None
    online, reason = _heuristic(status, text, final_url, url)
    if online is None:
        llm_res = _llm_check(text, llm)
        if llm_res is None:
            return None, None
        if llm_res is False:
            return False, "llm_inactive"
        return True, None
    return online, reason


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
            .filter(Application.status == ApplicationStatus.draft)
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

        online, reason = _check_one(app.url, llm)

        if online is not None:
            with _db() as db:
                fresh = db.get(Application, app.id)
                if fresh is not None:
                    fresh.posting_online = online
                    # Clear the reason when the posting is back online.
                    fresh.posting_offline_reason = None if online else reason
                    fresh.posting_checked_at = datetime.now(timezone.utc)
                    db.commit()

        checked += 1
        if i < len(apps) - 1:
            time.sleep(_RATE_LIMIT_SLEEP)

    return {"checked": checked, "skipped": skipped}
