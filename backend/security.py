"""Shared crypto helpers: API key hashing, generation, and JWT handling.

Kept separate from the auth router so the ownership dependency can verify API
keys without importing route handlers (avoids a circular import).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

# passlib 1.7.4 probes bcrypt's removed `__about__.__version__` for feature
# detection; on modern bcrypt it logs a trapped error that's purely cosmetic
# (hashing still works). Silence just that logger to keep startup logs clean.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.CRITICAL)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

API_KEY_PREFIX = "rk_"


# --- API keys -------------------------------------------------------------


def generate_api_key(org_id: str) -> str:
    """A fresh, unguessable API key of the form ``rk_<org_id>.<secret>``.

    The org id is embedded in the plaintext so an incoming key resolves to a
    single org in O(1) — bcrypt hashes are salted and can't be queried for, so
    without this we'd have to bcrypt-verify against every org. Only the bcrypt
    hash of the whole key is stored; the plaintext is shown to the org once.
    """
    return f"{API_KEY_PREFIX}{org_id}.{secrets.token_urlsafe(32)}"


def _split_key(api_key: str) -> tuple[str, str] | None:
    """Return (org_id, secret) for a well-formed key, else None."""
    if not api_key.startswith(API_KEY_PREFIX):
        return None
    body = api_key[len(API_KEY_PREFIX) :]
    org_id, sep, secret = body.partition(".")
    if not sep or not org_id or not secret:
        return None
    return org_id, secret


def parse_org_id(api_key: str) -> str | None:
    """Extract the org id embedded in a presented API key, or None if the key
    is malformed. Does NOT authenticate — the caller must still verify the
    secret against that org's stored hash."""
    parts = _split_key(api_key)
    return parts[0] if parts else None


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage. Only the random secret segment is hashed,
    not the full key: bcrypt silently truncates input at 72 bytes, and the
    fixed `rk_<uuid>.` prefix would otherwise eat into the secret's entropy
    window. The org id is parsed separately for lookup, so excluding it from
    the hash costs nothing and keeps the full ~256-bit secret protected."""
    parts = _split_key(api_key)
    if parts is None:
        raise ValueError("Malformed API key")
    return _pwd_context.hash(parts[1])


def verify_api_key(api_key: str, hashed: str) -> bool:
    parts = _split_key(api_key)
    if parts is None:
        return False
    try:
        return _pwd_context.verify(parts[1], hashed)
    except ValueError:
        # Malformed stored hash — treat as a non-match rather than crashing.
        return False


# --- JWT ------------------------------------------------------------------


def create_access_token(subject: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> str | None:
    """Returns the subject if the token is valid and unexpired, else None."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    return payload.get("sub")
