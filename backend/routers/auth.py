"""Admin auth (JWT) + org/API-key management.

`POST /auth/login` issues a 15-minute JWT to the bootstrap admin (credentials
from env). Org creation and key rotation require that JWT — they are
platform-admin operations, not org-self-service.
"""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from database import Organization, get_db
from middleware.rate_limit import LOGIN_LIMIT, limiter
from schemas import (
    CreateOrgRequest,
    LoginRequest,
    OrgCreatedResponse,
    RotatedKeyResponse,
    TokenResponse,
)
from security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
)

router = APIRouter(tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Validate the admin JWT on platform-admin routes."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = decode_access_token(creds.credentials)
    if subject != settings.ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def login(request: Request, body: LoginRequest) -> TokenResponse:
    # Constant-time comparison on both fields to avoid leaking which one was
    # wrong (and to blunt timing attacks).
    email_ok = hmac.compare_digest(body.email.lower(), settings.ADMIN_EMAIL.lower())
    pw_ok = hmac.compare_digest(body.password, settings.ADMIN_PASSWORD)
    if not (email_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    token, expires_in = create_access_token(settings.ADMIN_EMAIL)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post(
    "/orgs",
    response_model=OrgCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_org(
    body: CreateOrgRequest,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrgCreatedResponse:
    org = Organization(name=body.name, plan=body.plan, api_key="pending")
    db.add(org)
    db.flush()  # assigns org.id so we can embed it in the key

    api_key = generate_api_key(org.id)
    org.api_key = hash_api_key(api_key)
    db.commit()
    db.refresh(org)

    return OrgCreatedResponse(
        id=org.id, name=org.name, plan=org.plan, api_key=api_key
    )


@router.post("/orgs/{org_id}/rotate-key", response_model=RotatedKeyResponse)
def rotate_key(
    org_id: str,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RotatedKeyResponse:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Org not found."
        )
    api_key = generate_api_key(org.id)
    org.api_key = hash_api_key(api_key)
    db.commit()
    return RotatedKeyResponse(id=org.id, api_key=api_key)
