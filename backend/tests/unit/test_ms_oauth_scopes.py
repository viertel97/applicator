from unittest.mock import MagicMock

import app.auth.ms_oauth as mod
from app.auth.ms_oauth import (
    MSConfig,
    _msal_scopes,
    acquire_token_by_refresh_token,
)


def _cfg() -> MSConfig:
    return MSConfig(
        tenant_id="t", client_id="c", client_secret="s",
        redirect_uri="http://localhost/cb",
    )


def test_default_scopes_include_calendars_read():
    assert "Calendars.Read" in MSConfig.scopes


def test_msal_scopes_strip_reserved():
    # offline_access is reserved; MSAL would reject it if passed through.
    scopes = _msal_scopes(_cfg())
    assert "Calendars.Read" in scopes
    assert "offline_access" not in scopes


def test_acquire_token_by_refresh_token_uses_client(monkeypatch):
    fake_app = MagicMock()
    fake_app.acquire_token_by_refresh_token.return_value = {"access_token": "AT"}
    monkeypatch.setattr(mod, "_client", lambda cfg: fake_app)

    out = acquire_token_by_refresh_token(_cfg(), "RT")

    assert out == {"access_token": "AT"}
    fake_app.acquire_token_by_refresh_token.assert_called_once()
    _args, kwargs = fake_app.acquire_token_by_refresh_token.call_args
    assert kwargs["scopes"] == ["User.Read", "Calendars.Read"]
