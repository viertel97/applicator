from dataclasses import dataclass

import msal


@dataclass
class MSConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: tuple[str, ...] = ("User.Read",)


def authorize_url(cfg: MSConfig, state: str) -> str:
    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=cfg.client_secret,
    )
    return app.get_authorization_request_url(
        list(cfg.scopes), state=state, redirect_uri=cfg.redirect_uri
    )


def acquire_token_by_code(cfg: MSConfig, code: str) -> dict:
    app = msal.ConfidentialClientApplication(
        cfg.client_id,
        authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        client_credential=cfg.client_secret,
    )
    return app.acquire_token_by_authorization_code(
        code, scopes=list(cfg.scopes), redirect_uri=cfg.redirect_uri
    )
