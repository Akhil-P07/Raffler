"""Pydantic request/response models.

Every request body is validated here so routers never touch raw dicts.
Response models are explicit so internal columns (api_key hash, org_id on
public responses) never leak by accident.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Auth / orgs
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    plan: str = Field(default="free")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("plan")
    @classmethod
    def valid_plan(cls, v: str) -> str:
        if v not in ("free", "club"):
            raise ValueError("plan must be 'free' or 'club'")
        return v


class OrgCreatedResponse(BaseModel):
    id: str
    name: str
    plan: str
    # Plaintext API key — shown exactly once, never stored or retrievable again.
    api_key: str


class RotatedKeyResponse(BaseModel):
    id: str
    api_key: str


# ---------------------------------------------------------------------------
# Raffles
# ---------------------------------------------------------------------------


class CreateRaffleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class UpdateRaffleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    status: str | None = None

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


class RaffleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    drawn_at: datetime | None
    created_at: datetime


class RaffleDetailResponse(RaffleResponse):
    entry_count: int
    ticket_count: int


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


class GenerateTicketsRequest(BaseModel):
    count: int = Field(gt=0, le=10_000)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_number: int
    token: str
    registered: bool


class GenerateTicketsResponse(BaseModel):
    raffle_id: str
    created: int
    tickets: list[TicketResponse]


# ---------------------------------------------------------------------------
# Registration (public)
# ---------------------------------------------------------------------------


class RegisterInfoResponse(BaseModel):
    """Returned by GET /register/{token}. Deliberately minimal: no raffle_id,
    no ticket sequence, nothing that reveals the namespace."""

    ticket_number: int
    raffle_name: str
    registered: bool


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
