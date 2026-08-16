from dataclasses import dataclass

import msal

# MSAL requests these implicitly and raises if they are passed explicitly, so
# strip them before handing a scope list to any MSAL call.
_RESERVED_SCOPES = frozenset({"openid", "profile", "offline_access"})


@dataclass
class MSConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    # Calendars.Read lets the poller read the "Interviews" calendar;
    # offline_access documents intent to mint a refresh token so the Celery
    # beat task can sync without an interactive session (MSAL requests it
    # implicitly). Bumping these requires one re-login to re-consent.
    scopes: tuple[str, ...] = ("User.Read", "Calendars.Read", "offline_access")


def _msal_scopes(cfg: MSConfig) -> list[str]:
    return [s for s in cfg.scopes if s not in _RESERVED_SCOPES]


def _client(cfg: MSConfig) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=cfg.client_secret,
    )


def authorize_url(cfg: MSConfig, state: str) -> str:
    return _client(cfg).get_authorization_request_url(
        _msal_scopes(cfg), state=state, redirect_uri=cfg.redirect_uri
    )


def acquire_token_by_code(cfg: MSConfig, code: str) -> dict:
    return _client(cfg).acquire_token_by_authorization_code(
        code, scopes=_msal_scopes(cfg), redirect_uri=cfg.redirect_uri
    )


def acquire_token_by_refresh_token(cfg: MSConfig, refresh_token: str) -> dict:
    """Mint a fresh access token from a stored refresh token.

    Used by the calendar-sync task, which has no interactive session. Returns
    the raw MSAL token dict; callers check for ``access_token`` and surface
    ``error`` / ``error_description`` on failure (e.g. revoked consent).
    """
    return _client(cfg).acquire_token_by_refresh_token(
        refresh_token, scopes=_msal_scopes(cfg)
    )
