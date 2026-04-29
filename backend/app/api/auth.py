import base64
import hashlib
import hmac
import os
import struct
import time
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

_STATE_TTL_SECONDS = 600  # 10 minutes


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Re-add padding
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def generate_oauth_state(secret: str) -> str:
    """Return a tamper-evident, time-limited state token.

    Format: <random_b64>.<timestamp_b64>.<hmac_b64>
    The HMAC covers random + timestamp so neither can be altered independently.
    """
    random_bytes = os.urandom(16)
    timestamp = int(time.time())
    ts_bytes = struct.pack(">Q", timestamp)  # 8-byte big-endian uint64

    payload = random_bytes + ts_bytes
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()

    return (
        f"{_b64url_encode(random_bytes)}"
        f".{_b64url_encode(ts_bytes)}"
        f".{_b64url_encode(sig)}"
    )


def verify_oauth_state(state: str, secret: str) -> None:
    """Verify a state token produced by generate_oauth_state.

    Raises ValueError with a descriptive message on any failure.
    """
    parts = state.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid OAuth state: wrong format")

    try:
        random_bytes = _b64url_decode(parts[0])
        ts_bytes = _b64url_decode(parts[1])
        provided_sig = _b64url_decode(parts[2])
    except Exception as exc:
        raise ValueError(f"Invalid OAuth state: base64 decode error: {exc}") from exc

    if len(ts_bytes) != 8:
        raise ValueError("Invalid OAuth state: timestamp length mismatch")

    payload = random_bytes + ts_bytes
    expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid OAuth state: HMAC mismatch (possible forgery)")

    timestamp = struct.unpack(">Q", ts_bytes)[0]
    age = time.time() - timestamp
    if age > _STATE_TTL_SECONDS:
        raise ValueError(f"OAuth state expired ({age:.0f}s > {_STATE_TTL_SECONDS}s)")
    if age < -60:
        # Clock skew guard: state from more than 60 s in the future is suspicious
        raise ValueError("OAuth state timestamp is in the future")


def _ms_config(s: Settings) -> MSConfig:
    return MSConfig(
        tenant_id=s.ms_tenant_id,
        client_id=s.ms_client_id,
        client_secret=s.ms_client_secret,
        redirect_uri=s.ms_redirect_uri,
    )


@router.get("/login")
def login(settings: Annotated[Settings, Depends(settings_dep)]) -> RedirectResponse:
    state = generate_oauth_state(settings.app_secret_key)
    url = authorize_url(_ms_config(settings), state)
    return RedirectResponse(url=url)


@router.get("/callback")
def callback(
    response: Response,
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        raise HTTPException(400, f"oauth provider error: {error}: {error_description}")
    if not code or not state:
        raise HTTPException(400, "missing code or state")
    try:
        verify_oauth_state(state, settings.app_secret_key)
    except ValueError as exc:
        raise HTTPException(400, f"invalid state: {exc}") from exc

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
    redirect = RedirectResponse(url="/applications")
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
