"""Authentication: self-service signup (email+password or Google), login, the
admin-managed premium allowlist, and account/org self-service.

There are no API keys. Everyone can self-sign-up into the free tier; emails on
the premium allowlist (DB table ∪ the PREMIUM_EMAILS env list) get the club
plan. The plan is re-evaluated on every login so the admin can promote/demote.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import Organization, PremiumEmail, User, get_db
from middleware.ownership import get_session, require_org
from middleware.rate_limit import LOGIN_LIMIT, limiter
from schemas import (
    AdminLoginRequest,
    AuthResponse,
    GoogleAuthUrlResponse,
    LoginRequest,
    MeResponse,
    OrgSummary,
    PremiumEmailRequest,
    PremiumEmailResponse,
    SignupRequest,
    TokenResponse,
    UpdateOrgRequest,
)
from security import (
    create_admin_token,
    create_oauth_state,
    create_session_token,
    decode_admin_email,
    google_auth_url,
    google_exchange_code,
    hash_password,
    verify_oauth_state,
    verify_password,
)

router = APIRouter(tags=["auth"])

_bearer = HTTPBearer(auto_error=False)

# A fixed bcrypt hash to verify against when an email is unknown, so login
# takes the same time whether or not the account exists (no timing oracle).
_DUMMY_HASH = hash_password("not-a-real-password-placeholder")


# --- helpers --------------------------------------------------------------


def _norm(email: str) -> str:
    return email.strip().lower()


def _is_premium(db: Session, email: str) -> bool:
    email = _norm(email)
    if email in settings.premium_email_set:
        return True
    return (
        db.scalar(select(PremiumEmail.id).where(PremiumEmail.email == email))
        is not None
    )


def _plan_for(db: Session, email: str) -> str:
    return "club" if _is_premium(db, email) else "free"


def _auth_response(user: User, org: Organization) -> AuthResponse:
    token, expires_in = create_session_token(user.id, user.email, org.id)
    return AuthResponse(
        access_token=token,
        expires_in=expires_in,
        email=user.email,
        org=OrgSummary.model_validate(org),
    )


# --- email + password -----------------------------------------------------


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LOGIN_LIMIT)
def register(
    request: Request, body: SignupRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    email = _norm(body.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    org = Organization(
        name=body.org_name or email.split("@")[0],
        plan=_plan_for(db, email),
    )
    db.add(org)
    db.flush()
    user = User(
        email=email, password_hash=hash_password(body.password), org_id=org.id
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    return _auth_response(user, org)


@router.post("/auth/login", response_model=AuthResponse)
@limiter.limit(LOGIN_LIMIT)
def login(
    request: Request, body: LoginRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    email = _norm(body.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(body.password, _DUMMY_HASH)  # equalize timing
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    org = db.get(Organization, user.org_id)
    # Re-evaluate plan so allowlist changes take effect on next login.
    new_plan = _plan_for(db, email)
    if org.plan != new_plan:
        org.plan = new_plan
        db.commit()
    return _auth_response(user, org)


# --- Google OAuth ---------------------------------------------------------


_OAUTH_STATE_COOKIE = "raffler_oauth_state"


@router.get("/auth/google/login", response_model=GoogleAuthUrlResponse)
def google_login(response: Response) -> GoogleAuthUrlResponse:
    if not settings.google_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google login is not configured.",
        )
    state, _ = create_oauth_state()
    # Bind the state to this browser via an HttpOnly cookie so the callback can
    # confirm the flow was started here (CSRF / forced-login protection).
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.API_ORIGIN.startswith("https"),
    )
    return GoogleAuthUrlResponse(auth_url=google_auth_url(state))


@router.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    front = settings.FRONTEND_ORIGIN.rstrip("/")

    def _fail(reason: str) -> RedirectResponse:
        resp = RedirectResponse(url=f"{front}/login?error={reason}")
        resp.delete_cookie(_OAUTH_STATE_COOKIE)
        return resp

    # Google isn't configured → bounce to the login page, not a raw JSON 503.
    if not settings.google_enabled:
        return _fail("google_failed")
    # State must be present, validly signed, AND match the cookie set at login.
    cookie_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if (
        error
        or not code
        or not state
        or not verify_oauth_state(state)
        or state != cookie_state
    ):
        return _fail("google_failed")

    try:
        profile = google_exchange_code(code)
    except ValueError:
        return _fail("google_failed")
    if not profile.get("email_verified"):
        return _fail("email_unverified")

    email = _norm(profile["email"])
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        org = Organization(
            name=profile.get("name") or email.split("@")[0],
            plan=_plan_for(db, email),
        )
        db.add(org)
        db.flush()
        user = User(email=email, google_sub=profile.get("sub"), org_id=org.id)
        db.add(user)
        db.commit()
        db.refresh(org)
    else:
        org = db.get(Organization, user.org_id)
        if user.google_sub is None:
            user.google_sub = profile.get("sub")
        new_plan = _plan_for(db, email)
        if org.plan != new_plan:
            org.plan = new_plan
        db.commit()

    token, _ = create_session_token(user.id, user.email, org.id)
    # Hand the token to the SPA via the URL *fragment* (after #): fragments are
    # never sent to servers, so the token can't leak into access logs or the
    # Referer header the way a query param would. The state cookie is cleared.
    resp = RedirectResponse(url=f"{front}/auth/callback#token={token}")
    resp.delete_cookie(_OAUTH_STATE_COOKIE)
    return resp


# --- account / org self-service -------------------------------------------


@router.get("/me", response_model=MeResponse)
def me(
    claims: dict[str, Any] = Depends(get_session),
    org: Organization = Depends(require_org),
) -> MeResponse:
    return MeResponse(email=claims["email"], org=OrgSummary.model_validate(org))


@router.patch("/org", response_model=OrgSummary)
def update_org(
    body: UpdateOrgRequest,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> OrgSummary:
    if body.name is not None:
        org.name = body.name
    if "goc_id" in body.model_fields_set:
        org.goc_id = body.goc_id
    db.commit()
    db.refresh(org)
    return OrgSummary.model_validate(org)


# --- super-admin: premium allowlist ---------------------------------------


def require_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = decode_admin_email(creds.credentials)
    if email != settings.ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return email


@router.post("/auth/admin/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def admin_login(request: Request, body: AdminLoginRequest) -> TokenResponse:
    import hmac

    ok = hmac.compare_digest(
        _norm(body.email), settings.ADMIN_EMAIL.lower()
    ) and hmac.compare_digest(body.password, settings.ADMIN_PASSWORD)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials."
        )
    token, expires_in = create_admin_token(settings.ADMIN_EMAIL)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/admin/premium", response_model=list[PremiumEmailResponse])
def list_premium(
    _admin: str = Depends(require_admin), db: Session = Depends(get_db)
) -> list[PremiumEmailResponse]:
    rows = db.scalars(select(PremiumEmail).order_by(PremiumEmail.email)).all()
    result = [
        PremiumEmailResponse(email=r.email, source="allowlist") for r in rows
    ]
    # Surface env-configured premium emails too (read-only).
    db_emails = {r.email for r in rows}
    for e in sorted(settings.premium_email_set):
        if e not in db_emails:
            result.append(PremiumEmailResponse(email=e, source="env"))
    return result


@router.post(
    "/admin/premium",
    response_model=PremiumEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_premium(
    body: PremiumEmailRequest,
    response: Response,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PremiumEmailResponse:
    email = _norm(body.email)
    existing = db.scalar(select(PremiumEmail).where(PremiumEmail.email == email))
    if existing is not None:
        # Idempotent: already on the allowlist -> 200, not 201.
        response.status_code = status.HTTP_200_OK
        return PremiumEmailResponse(email=email, source="allowlist")

    db.add(PremiumEmail(email=email))
    # Promote an existing account immediately.
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        org = db.get(Organization, user.org_id)
        if org is not None:
            org.plan = "club"
    db.commit()
    return PremiumEmailResponse(email=email, source="allowlist")


@router.delete(
    "/admin/premium/{email}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_premium(
    email: str,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    email = _norm(email)
    row = db.scalar(select(PremiumEmail).where(PremiumEmail.email == email))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email is not on the allowlist.",
        )
    db.delete(row)
    # Demote unless still premium via the env list.
    if email not in settings.premium_email_set:
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            org = db.get(Organization, user.org_id)
            if org is not None:
                org.plan = "free"
    db.commit()
    return None
