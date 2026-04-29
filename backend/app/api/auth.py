import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.auth.ms_oauth import MSConfig, acquire_token_by_code, authorize_url
from app.auth.session import create_session, delete_session
from app.config import Settings
from app.crypto import encrypt
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_oauth_states: dict[str, bool] = {}  # in-memory; OK for single-user MVP


def _ms_config(s: Settings) -> MSConfig:
    return MSConfig(
        tenant_id=s.ms_tenant_id,
        client_id=s.ms_client_id,
        client_secret=s.ms_client_secret,
        redirect_uri=s.ms_redirect_uri,
    )


@router.get("/login")
def login(settings: Annotated[Settings, Depends(settings_dep)]) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = True
    url = authorize_url(_ms_config(settings), state)
    return RedirectResponse(url=url)


@router.get("/callback")
def callback(
    code: str,
    state: str,
    response: Response,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    if not _oauth_states.pop(state, False):
        raise HTTPException(400, "invalid state")
    token = acquire_token_by_code(_ms_config(settings), code)
    if "id_token_claims" not in token:
        raise HTTPException(400, f"oauth failed: {token.get('error_description')}")
    claims = token["id_token_claims"]
    oid = claims["oid"]
    email = claims.get("preferred_username") or claims.get("email") or ""
    name = claims.get("name") or email
    user = db.query(User).filter_by(ms_oid=oid).first()
    refresh = token.get("refresh_token")
    refresh_enc = encrypt(refresh, settings.app_secret_key) if refresh else None
    if user is None:
        user = User(
            ms_oid=oid, email=email, display_name=name, ms_refresh_token_encrypted=refresh_enc
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = email
        user.display_name = name
        if refresh_enc:
            user.ms_refresh_token_encrypted = refresh_enc
        db.commit()
    sid = create_session(db, user.id)
    redirect = RedirectResponse(url=settings.frontend_origin + "/applications")
    redirect.set_cookie(
        settings.session_cookie_name, sid,
        httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/",
    )
    return redirect


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> dict:
    sid = request.cookies.get(settings.session_cookie_name)
    if sid:
        delete_session(db, sid)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> dict:
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}
