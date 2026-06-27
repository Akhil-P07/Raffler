"""Authentication & org membership.

Self-service signup (email+password or Google) creates an account that OWNS a
new organization. A user can belong to several orgs via Membership rows; the
session token names the currently-selected org. Owners can invite emails, who
join as members by accepting an emailed link. The premium allowlist grants the
club plan to the orgs an allowlisted email owns. No API keys — all
session-based.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from database import (
    Membership,
    OrgInvite,
    Organization,
    PremiumEmail,
    Raffle,
    User,
    get_db,
)
from middleware.ownership import get_session, require_org, require_owner
from middleware.rate_limit import LOGIN_LIMIT, limiter
from schemas import (
    AcceptInviteRequest,
    AdminLoginRequest,
    AuthResponse,
    ForgotPasswordRequest,
    GoogleAuthUrlResponse,
    InviteInfoResponse,
    LoginRequest,
    MeResponse,
    MessageResponse,
    OrgMembershipSummary,
    OrgMemberRequest,
    OrgMemberResponse,
    OrgSummary,
    PlanUsageResponse,
    PremiumEmailRequest,
    PremiumEmailResponse,
    ResetPasswordRequest,
    SelectOrgRequest,
    SignupRequest,
    TokenResponse,
    UpdateOrgRequest,
)
from security import (
    create_admin_token,
    create_oauth_state,
    create_password_reset_token,
    create_session_token,
    decode_admin_email,
    decode_password_reset_token,
    google_auth_url,
    google_exchange_code,
    hash_password,
    verify_oauth_state,
    verify_password,
)
from services.email import send_invite_email, send_password_reset_email
from services.limits import PLAN_LIMITS

router = APIRouter(tags=["auth"])

logger = logging.getLogger("raffler.auth")

_bearer = HTTPBearer(auto_error=False)

# A fixed bcrypt hash to verify against when an email is unknown, so login
# takes the same time whether or not the account exists (no timing oracle).
_DUMMY_HASH = hash_password("not-a-real-password-placeholder")

_OAUTH_STATE_COOKIE = "raffler_oauth_state"

# Invites expire so a forwarded accept link can't be redeemed indefinitely.
_INVITE_TTL = timedelta(days=7)


# --- helpers --------------------------------------------------------------


def _norm(email: str) -> str:
    return email.strip().lower()


def _invite_expired(invite: OrgInvite) -> bool:
    created = invite.created_at
    if created is None:
        return False
    if created.tzinfo is None:  # SQLite stores naive timestamps
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created > _INVITE_TTL


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


def _membership(db: Session, user_id: str, org_id: str) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.user_id == user_id, Membership.org_id == org_id
        )
    )


def _memberships(db: Session, user_id: str) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
        ).all()
    )


def _org_summaries(db: Session, user_id: str) -> list[OrgMembershipSummary]:
    rows = db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.created_at)
    ).all()
    return [
        OrgMembershipSummary(
            id=o.id, name=o.name, plan=o.plan, goc_id=o.goc_id, role=role
        )
        for o, role in rows
    ]


def _default_or_create_membership(db: Session, user: User) -> Membership:
    """The membership a login defaults to: an owner org if any, else the first.
    If the user has no orgs at all (e.g. all memberships removed), give them a
    fresh personal org so they're never locked out."""
    ms = _memberships(db, user.id)
    if not ms:
        org = Organization(
            name=user.email.split("@")[0], plan=_plan_for(db, user.email)
        )
        db.add(org)
        db.flush()
        m = Membership(user_id=user.id, org_id=org.id, role="owner")
        db.add(m)
        db.commit()
        return m
    owners = [m for m in ms if m.role == "owner"]
    return owners[0] if owners else ms[0]


def _reeval_owner_plan(db: Session, membership: Membership, email: str) -> None:
    """Keep an owned org's plan in sync with the owner's allowlist status."""
    if membership.role != "owner":
        return
    org = db.get(Organization, membership.org_id)
    plan = _plan_for(db, email)
    if org is not None and org.plan != plan:
        org.plan = plan
        db.commit()


def _auth_response(db: Session, user: User, membership: Membership) -> AuthResponse:
    org = db.get(Organization, membership.org_id)
    token, expires_in = create_session_token(
        user.id, user.email, org.id, membership.role
    )
    return AuthResponse(
        access_token=token,
        expires_in=expires_in,
        email=user.email,
        role=membership.role,
        org=OrgSummary.model_validate(org),
        orgs=_org_summaries(db, user.id),
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
        name=body.org_name or email.split("@")[0], plan=_plan_for(db, email)
    )
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, org_id=org.id, role="owner")
    db.add(membership)
    db.commit()
    return _auth_response(db, user, membership)


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
    membership = _default_or_create_membership(db, user)
    _reeval_owner_plan(db, membership, email)
    return _auth_response(db, user, membership)


@router.post("/auth/select-org", response_model=AuthResponse)
def select_org(
    body: SelectOrgRequest,
    claims: dict[str, Any] = Depends(get_session),
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Switch the session to a different org the user belongs to."""
    user = db.get(User, claims["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    membership = _membership(db, user.id, body.org_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of that organization.",
        )
    return _auth_response(db, user, membership)


# --- forgot / reset password ----------------------------------------------


def _pwd_fingerprint(user: User) -> str:
    """A short digest of the user's current credential state. It changes the
    moment the password hash changes, so a reset link can't be replayed once
    it's been used (the new hash no longer matches the token's fingerprint)."""
    basis = user.password_hash or f"nopw:{user.id}"
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


@router.post("/auth/forgot-password", response_model=MessageResponse)
@limiter.limit(LOGIN_LIMIT)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Email a password-reset link if the address has an account. Always returns
    the same message so it can't be used to probe which emails are registered."""
    email = _norm(body.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        token, _ = create_password_reset_token(user.id, _pwd_fingerprint(user))
        front = settings.FRONTEND_ORIGIN.rstrip("/")
        reset_url = f"{front}/reset-password?token={token}"
        background.add_task(send_password_reset_email, user.email, reset_url)
    return MessageResponse(
        message="If an account exists for that email, a reset link is on its way."
    )


@router.post("/auth/reset-password", response_model=MessageResponse)
@limiter.limit(LOGIN_LIMIT)
def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Set a new password from a valid reset token."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid or has expired. Request a new one.",
    )
    claims = decode_password_reset_token(body.token)
    if claims is None:
        raise invalid
    user = db.get(User, claims["sub"])
    # A fingerprint mismatch means the link was already used or the password has
    # since changed — reject it either way.
    if user is None or claims.get("fp") != _pwd_fingerprint(user):
        raise invalid
    user.password_hash = hash_password(body.password)
    db.commit()
    return MessageResponse(
        message="Your password has been reset. You can now sign in."
    )


# --- Google OAuth ---------------------------------------------------------


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
    #
    # Frontend and backend are separate origins in production, so the cookie
    # must ride the cross-site Google→backend redirect: that requires
    # SameSite=None + Secure (only valid over HTTPS). Locally (http) fall back
    # to Lax, which a browser won't drop for being non-Secure.
    https = settings.API_ORIGIN.startswith("https")
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="none" if https else "lax",
        secure=https,
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

    def _fail(reason: str, detail: str) -> RedirectResponse:
        # Log WHY (server-side only); the user just gets a generic error code.
        logger.warning("Google OAuth callback failed (%s): %s", reason, detail)
        resp = RedirectResponse(url=f"{front}/login?error={reason}")
        resp.delete_cookie(_OAUTH_STATE_COOKIE)
        return resp

    if not settings.google_enabled:
        return _fail("google_failed", "Google OAuth is not configured")
    if error:
        return _fail("google_failed", f"Google returned error={error}")
    if not code or not state:
        return _fail("google_failed", "missing code or state in callback")
    if not verify_oauth_state(state):
        return _fail("google_failed", "state JWT invalid or expired")
    # Best-effort per-browser binding. When the state cookie rides back, it must
    # match. But when the frontend and backend are on different sites (e.g. two
    # *.up.railway.app subdomains, which are cross-site), the browser drops the
    # backend's third-party cookie, so it's usually absent. The state itself is
    # a server-signed, short-lived JWT (verified above), which already blocks
    # forged or replayed states — so we proceed without the cookie rather than
    # lock everyone out. Serving both apps under one registrable domain
    # (app.example.com + api.example.com) makes the cookie first-party again and
    # restores the stricter binding automatically.
    cookie_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if cookie_state is not None and state != cookie_state:
        return _fail("google_failed", "state cookie present but mismatched")

    try:
        profile = google_exchange_code(code)
    except ValueError as exc:
        # Usually a GOOGLE_REDIRECT_URI / client-secret mismatch with the
        # Google Cloud console, which makes the token exchange return non-200.
        return _fail("google_failed", f"token exchange/profile fetch failed: {exc}")
    if not profile.get("email_verified"):
        return _fail("email_unverified", "Google account email is not verified")

    email = _norm(profile["email"])
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        org = Organization(
            name=profile.get("name") or email.split("@")[0],
            plan=_plan_for(db, email),
        )
        db.add(org)
        db.flush()
        user = User(email=email, google_sub=profile.get("sub"))
        db.add(user)
        db.flush()
        membership = Membership(user_id=user.id, org_id=org.id, role="owner")
        db.add(membership)
        db.commit()
    else:
        if user.google_sub is None:
            user.google_sub = profile.get("sub")
            db.commit()
        membership = _default_or_create_membership(db, user)
        _reeval_owner_plan(db, membership, email)

    org = db.get(Organization, membership.org_id)
    token, _ = create_session_token(user.id, user.email, org.id, membership.role)
    # Token via the URL *fragment* — fragments aren't sent to servers, so it
    # can't leak into access logs or the Referer header. State cookie cleared.
    resp = RedirectResponse(url=f"{front}/auth/callback#token={token}")
    resp.delete_cookie(_OAUTH_STATE_COOKIE)
    return resp


# --- current account / org ------------------------------------------------


@router.get("/me", response_model=MeResponse)
def me(
    claims: dict[str, Any] = Depends(get_session),
    db: Session = Depends(get_db),
) -> MeResponse:
    user = db.get(User, claims["sub"])
    org = db.get(Organization, claims["org_id"])
    membership = _membership(db, claims["sub"], claims["org_id"])
    if user is None or org is None or membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return MeResponse(
        email=user.email,
        role=membership.role,
        org=OrgSummary.model_validate(org),
        orgs=_org_summaries(db, user.id),
    )


@router.get("/org/usage", response_model=PlanUsageResponse)
def org_usage(
    org: Organization = Depends(require_org), db: Session = Depends(get_db)
) -> PlanUsageResponse:
    """Current plan usage for the settings tracker. The raffle count is the
    lifetime total (all raffles ever created, including soft-deleted and drawn),
    matching how the free raffle cap is enforced."""
    limits = PLAN_LIMITS.get(org.plan, PLAN_LIMITS["free"])
    used = (
        db.scalar(
            select(func.count()).select_from(Raffle).where(Raffle.org_id == org.id)
        )
        or 0
    )
    return PlanUsageResponse(
        plan=org.plan,
        lifetime_raffles_used=used,
        lifetime_raffles_limit=limits["lifetime_raffles"],
        tickets_per_raffle_limit=limits["tickets_per_raffle"],
    )


@router.patch("/org", response_model=OrgSummary)
def update_org(
    body: UpdateOrgRequest,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> OrgSummary:
    if body.name is not None:
        org.name = body.name
    if "goc_id" in body.model_fields_set:
        org.goc_id = body.goc_id
    db.commit()
    db.refresh(org)
    return OrgSummary.model_validate(org)


# --- org members + invites -------------------------------------------------


@router.get("/org/members", response_model=list[OrgMemberResponse])
def list_members(
    org: Organization = Depends(require_owner), db: Session = Depends(get_db)
) -> list[OrgMemberResponse]:
    rows = db.execute(
        select(User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org.id)
        .order_by(Membership.created_at)
    ).all()
    members = {email for email, _ in rows}
    result = [OrgMemberResponse(email=email, status=role) for email, role in rows]
    invites = db.scalars(
        select(OrgInvite).where(OrgInvite.org_id == org.id)
    ).all()
    result += [
        OrgMemberResponse(email=i.email, status="invited")
        for i in invites
        if i.email not in members
    ]
    return result


@router.post(
    "/org/members",
    response_model=OrgMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    body: OrgMemberRequest,
    background: BackgroundTasks,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> OrgMemberResponse:
    email = _norm(body.email)
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None and _membership(db, existing_user.id, org.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That person is already a member of this organization.",
        )
    invite = db.scalar(
        select(OrgInvite).where(
            OrgInvite.org_id == org.id, OrgInvite.email == email
        )
    )
    if invite is None:
        invite = OrgInvite(org_id=org.id, email=email)
        db.add(invite)
        db.commit()
        db.refresh(invite)

    front = settings.FRONTEND_ORIGIN.rstrip("/")
    accept_url = f"{front}/accept-invite?token={invite.token}"
    background.add_task(send_invite_email, email, org.name, accept_url)
    return OrgMemberResponse(email=email, status="invited")


@router.delete(
    "/org/members/{email}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    email: str,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    email = _norm(email)
    # Drop any pending invite.
    invite = db.scalar(
        select(OrgInvite).where(
            OrgInvite.org_id == org.id, OrgInvite.email == email
        )
    )
    if invite is not None:
        db.delete(invite)

    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        membership = _membership(db, user.id, org.id)
        if membership is not None:
            if membership.role == "owner":
                owner_count = (
                    db.query(Membership)
                    .filter(
                        Membership.org_id == org.id, Membership.role == "owner"
                    )
                    .count()
                )
                if owner_count <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot remove the organization's only owner.",
                    )
            db.delete(membership)
    db.commit()
    return None


@router.get("/invites/{token}", response_model=InviteInfoResponse)
def invite_info(token: str, db: Session = Depends(get_db)) -> InviteInfoResponse:
    invite = db.scalar(select(OrgInvite).where(OrgInvite.token == token))
    if invite is None or _invite_expired(invite):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or expired.",
        )
    org = db.get(Organization, invite.org_id)
    user = db.scalar(select(User).where(User.email == invite.email))
    return InviteInfoResponse(
        email=invite.email,
        org_name=org.name if org else "",
        needs_password=user is None,
    )


@router.post("/invites/{token}/accept", response_model=AuthResponse)
@limiter.limit(LOGIN_LIMIT)
def accept_invite(
    request: Request,
    token: str,
    body: AcceptInviteRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    invite = db.scalar(select(OrgInvite).where(OrgInvite.token == token))
    if invite is None or _invite_expired(invite):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or expired.",
        )
    email = _norm(invite.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # New account: a password is required.
        if not body.password or len(body.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A password of at least 8 characters is required.",
            )
        user = User(email=email, password_hash=hash_password(body.password))
        db.add(user)
        db.flush()

    membership = _membership(db, user.id, invite.org_id)
    if membership is None:
        membership = Membership(
            user_id=user.id, org_id=invite.org_id, role="member"
        )
        db.add(membership)
    db.delete(invite)
    db.commit()
    return _auth_response(db, user, membership)


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


def _set_plan_for_owned_orgs(db: Session, email: str, plan: str) -> None:
    """Set the plan on every org the email is an owner of."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return
    rows = db.scalars(
        select(Membership).where(
            Membership.user_id == user.id, Membership.role == "owner"
        )
    ).all()
    for m in rows:
        org = db.get(Organization, m.org_id)
        if org is not None:
            org.plan = plan


@router.post("/auth/admin/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def admin_login(request: Request, body: AdminLoginRequest) -> TokenResponse:
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
    result = [PremiumEmailResponse(email=r.email, source="allowlist") for r in rows]
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
        response.status_code = status.HTTP_200_OK
        return PremiumEmailResponse(email=email, source="allowlist")

    db.add(PremiumEmail(email=email))
    _set_plan_for_owned_orgs(db, email, "club")  # promote immediately
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
    if email not in settings.premium_email_set:
        _set_plan_for_owned_orgs(db, email, "free")  # demote
    db.commit()
    return None
