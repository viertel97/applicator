import types
from unittest.mock import MagicMock

import pytest

from app.services.tokens import ensure_calendar_token, ensure_ingest_token, new_token, regenerate


def test_new_token_is_urlsafe_and_unique():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 32
    assert all(c.isalnum() or c in "-_" for c in a)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**kwargs):
    defaults = dict(ingest_token=None, calendar_token=None)
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_db():
    return MagicMock()


# ---------------------------------------------------------------------------
# ensure_ingest_token
# ---------------------------------------------------------------------------

def test_ensure_ingest_token_sets_and_commits_when_absent():
    user = _make_user(ingest_token=None)
    db = _make_db()

    token = ensure_ingest_token(db, user)

    assert token is not None
    assert len(token) >= 32
    db.commit.assert_called_once()
    assert user.ingest_token == token


def test_ensure_ingest_token_returns_existing_without_commit():
    existing = "already-set-token"
    user = _make_user(ingest_token=existing)
    db = _make_db()

    token = ensure_ingest_token(db, user)

    assert token == existing
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# ensure_calendar_token (mirrors ingest for symmetry)
# ---------------------------------------------------------------------------

def test_ensure_calendar_token_sets_and_commits_when_absent():
    user = _make_user(calendar_token=None)
    db = _make_db()

    token = ensure_calendar_token(db, user)

    assert token is not None
    assert len(token) >= 32
    db.commit.assert_called_once()
    assert user.calendar_token == token


def test_ensure_calendar_token_returns_existing_without_commit():
    existing = "cal-token-already-set"
    user = _make_user(calendar_token=existing)
    db = _make_db()

    token = ensure_calendar_token(db, user)

    assert token == existing
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# regenerate
# ---------------------------------------------------------------------------

def test_regenerate_ingest_sets_new_token_and_commits():
    user = _make_user(ingest_token="old-ingest")
    db = _make_db()

    regenerate(db, user, "ingest")

    assert user.ingest_token != "old-ingest"
    assert user.ingest_token is not None
    db.commit.assert_called_once()


def test_regenerate_calendar_sets_new_token_and_commits():
    user = _make_user(calendar_token="old-cal")
    db = _make_db()

    regenerate(db, user, "calendar")

    assert user.calendar_token != "old-cal"
    assert user.calendar_token is not None
    db.commit.assert_called_once()


def test_regenerate_bad_kind_raises_value_error_and_does_not_commit():
    user = _make_user()
    db = _make_db()

    with pytest.raises(ValueError, match="unknown token kind"):
        regenerate(db, user, "bad")

    db.commit.assert_not_called()
