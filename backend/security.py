"""Shared auth helpers: password hashing, JWT sessions, OAuth state, and the
Google OAuth code exchange.

Kept separate from the auth router so the ownership dependency can decode
session tokens without importing route handlers (avoids a circular import).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

# passlib 1.7.4 probes bcrypt's removed `__about__.__version__` for feature
# detection; on modern bcrypt it logs a trapped error that's purely cosmetic
# (hashing still works). Silence just that logger to keep startup logs clean.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.CRITICAL)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


# --- passwords ------------------------------------------------------------


def hash_password(password: str) -> str:
    # bcrypt truncates at 72 bytes; callers cap password length in the schema.
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(password, hashed)
    except ValueError:
        return False


# --- JWT: sessions, admin, and OAuth state --------------------------------


def _encode(payload: dict[str, Any], expires_delta: timedelta) -> tuple[str, int]:
    to_encode = dict(payload)
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    token = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token, int(expires_delta.total_seconds())


def create_session_token(
    user_id: str, email: str, org_id: str, role: str
) -> tuple[str, int]:
    """Session token for a logged-in user. Returns (token, expires_in_seconds)."""
    return _encode(
        {
            "typ": "session",
            "sub": user_id,
            "email": email,
            "org_id": org_id,
            "role": role,
        },
        timedelta(minutes=settings.SESSION_TOKEN_EXPIRE_MINUTES),
    )


def decode_session_token(token: str) -> dict[str, Any] | None:
    """Return the session claims if valid+unexpired and of type 'session'."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("typ") != "session" or "org_id" not in payload:
        return None
    return payload


def create_admin_token(email: str) -> tuple[str, int]:
    return _encode(
        {"typ": "admin", "sub": email},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def decode_admin_email(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("typ") != "admin":
        return None
    return payload.get("sub")


def create_oauth_state() -> tuple[str, int]:
    """Short-lived signed state for CSRF protection on the Google flow."""
    return _encode(
        {"typ": "oauth_state", "nonce": secrets.token_urlsafe(16)},
        timedelta(minutes=10),
    )


def verify_oauth_state(token: str) -> bool:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return False
    return payload.get("typ") == "oauth_state"


def create_password_reset_token(user_id: str, fingerprint: str) -> tuple[str, int]:
    """Short-lived signed token for a password-reset link. The fingerprint binds
    it to the user's current credential state, so the link stops working once
    the password is changed — i.e. it's effectively single-use."""
    return _encode(
        {"typ": "pwd_reset", "sub": user_id, "fp": fingerprint},
        timedelta(minutes=30),
    )


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    """Return the reset-token claims if valid, unexpired, and of type 'pwd_reset'."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("typ") != "pwd_reset" or "sub" not in payload:
        return None
    return payload


# --- Google OAuth ---------------------------------------------------------


def google_auth_url(state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def google_exchange_code(code: str) -> dict[str, Any]:
    """Exchange an auth code for tokens, then fetch the user's profile.

    Returns {'email', 'email_verified', 'sub', 'name'}. Raises ValueError on
    any failure. Isolated here so tests can monkeypatch it.
    """
    with httpx.Client(timeout=10) as client:
        token_resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise ValueError("Google token exchange failed")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("No access token from Google")

        info_resp = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            raise ValueError("Could not fetch Google profile")
        info = info_resp.json()

    if not info.get("email"):
        raise ValueError("Google profile has no email")
    return {
        "email": info["email"],
        "email_verified": bool(info.get("email_verified", False)),
        "sub": info.get("sub"),
        "name": info.get("name"),
    }
