"""Pydantic request/response models.

Every request body is validated here so routers never touch raw dicts.
Response models are explicit so internal columns (api_key hash, org_id on
public responses) never leak by accident.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Auth (user accounts) + admin allowlist
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    """Account self-signup (email + password). Distinct from the buyer-facing
    RegisterRequest used by the public /register/{token} flow."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # Optional org/club name shown on tickets; defaults to the email's prefix.
    org_name: str | None = Field(default=None, max_length=120)

    @field_validator("org_name")
    @classmethod
    def strip_org_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class OrgSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plan: str
    goc_id: str | None


class OrgMembershipSummary(BaseModel):
    """An org the user belongs to, with their role in it (for the switcher)."""

    id: str
    name: str
    plan: str
    goc_id: str | None
    role: str  # 'owner' | 'member'


class AuthResponse(BaseModel):
    """Returned by register/login/select-org — a session token scoped to the
    currently-selected org, plus the full list of orgs the user belongs to."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    email: EmailStr
    role: str  # role in the current org
    org: OrgSummary  # current org
    orgs: list[OrgMembershipSummary]


class TokenResponse(BaseModel):
    """Bare token (admin login)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SelectOrgRequest(BaseModel):
    org_id: str


class MeResponse(BaseModel):
    email: EmailStr
    role: str  # role in the current org
    org: OrgSummary
    orgs: list[OrgMembershipSummary]


class OrgMemberRequest(BaseModel):
    email: EmailStr


class OrgMemberResponse(BaseModel):
    email: EmailStr
    # 'owner' | 'member' (an existing account) or 'invited' (pending signup).
    status: str


class InviteInfoResponse(BaseModel):
    email: EmailStr
    org_name: str
    needs_password: bool  # true when the email has no account yet


class AcceptInviteRequest(BaseModel):
    # Required only when creating a new account (needs_password); ignored for an
    # existing account (the emailed token proves email control).
    password: str | None = Field(default=None, max_length=128)


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    goc_id: str | None = Field(default=None, max_length=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("goc_id")
    @classmethod
    def strip_goc(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class PremiumEmailRequest(BaseModel):
    email: EmailStr


class PremiumEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    source: str = "allowlist"  # 'allowlist' (DB) or 'env'


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str


# ---------------------------------------------------------------------------
# Raffles
# ---------------------------------------------------------------------------


def _blank_to_none(v: str | None) -> str | None:
    """Strip a text field; treat empty/whitespace as None (field omitted)."""
    if v is None:
        return None
    v = v.strip()
    return v or None


class CreateRaffleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Legal ticket-face metadata (all optional; printed when present).
    ticket_price: str | None = Field(default=None, max_length=20)
    prizes: str | None = Field(default=None, max_length=500)
    drawing_datetime: datetime | None = None
    drawing_location: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("ticket_price", "prizes", "drawing_location")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class UpdateRaffleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    status: str | None = None
    ticket_price: str | None = Field(default=None, max_length=20)
    prizes: str | None = Field(default=None, max_length=500)
    drawing_datetime: datetime | None = None
    drawing_location: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str | None) -> str | None:
        # 'drawn' is set only by the draw endpoint, never by a manual update.
        if v is not None and v not in ("active", "closed"):
            raise ValueError("status must be 'active' or 'closed'")
        return v

    @field_validator("ticket_price", "prizes", "drawing_location")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class RaffleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    ticket_price: str | None
    prizes: str | None
    drawing_datetime: datetime | None
    drawing_location: str | None
    drawn_at: datetime | None
    created_at: datetime


class RaffleDetailResponse(RaffleResponse):
    entry_count: int
    ticket_count: int


class RaffleLogoResponse(BaseModel):
    """Logo metadata only — the image bytes are served by a separate endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str | None
    position: int


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


class GenerateTicketsRequest(BaseModel):
    count: int = Field(gt=0, le=10_000)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_number: int
    registered: bool
    # NOTE: the unguessable `token` is deliberately NOT exposed. It only ever
    # lives inside the server-rendered QR image / print sheet, so dumping every
    # token in a list response can't leak the registration boundary.


class GenerateTicketsResponse(BaseModel):
    raffle_id: str
    created: int
    tickets: list[TicketResponse]


# ---------------------------------------------------------------------------
# Registration (public)
# ---------------------------------------------------------------------------


class RegisterInfoResponse(BaseModel):
    """Returned by GET /register/{token} to a logged-in seller. `owned` says
    whether the ticket belongs to the seller's own org; ticket/raffle details
    are only included when owned (a ticket from another org reveals nothing).
    When already registered, the registrant's name + email are returned so a
    re-scan shows who the ticket belongs to."""

    owned: bool
    ticket_number: int | None = None
    raffle_name: str | None = None
    registered: bool | None = None
    registrant_name: str | None = None
    registrant_email: str | None = None


class RegisterRequest(BaseModel):
    name: str = Field(max_length=100)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class RegisterConfirmation(BaseModel):
    ticket_number: int
    raffle_name: str
    name: str
    message: str = "Registration successful. Good luck!"


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


class EntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    ticket_number: int
    registered_at: datetime


class DeregisterRequest(BaseModel):
    """Owner-only bulk undo of registrations (system-failure recovery)."""

    entry_ids: list[str] = Field(min_length=1, max_length=10_000)


class DeregisterResponse(BaseModel):
    deregistered: int


# ---------------------------------------------------------------------------
# Draw / winners
# ---------------------------------------------------------------------------


class DrawRequest(BaseModel):
    prize_count: int = Field(default=1, ge=1, le=100)


class WinnerResponse(BaseModel):
    id: str
    prize_rank: int
    name: str
    email: str
    ticket_number: int
    drawn_at: datetime


class DrawResponse(BaseModel):
    raffle_id: str
    status: str
    already_drawn: bool
    winners: list[WinnerResponse]
