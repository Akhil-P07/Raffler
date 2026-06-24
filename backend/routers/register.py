"""Public, token-based buyer registration. No API key required.

The token is validated against its expected charset/length *before* any DB
lookup, so malformed tokens are rejected without touching the database. The
endpoint never exposes raffle_id, ticket sequence, or any other token.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Entry, Raffle, Ticket, get_db
from middleware.rate_limit import REGISTER_LIMIT, limiter
from schemas import RegisterConfirmation, RegisterInfoResponse, RegisterRequest

router = APIRouter(tags=["registration"])

# token_urlsafe(24) -> exactly 32 chars from the URL-safe base64 alphabet.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found."
)


def _validate_token(token: str) -> None:
    if not _TOKEN_RE.match(token):
        # Same 404 as an unknown token so length/charset can't be probed.
        raise _NOT_FOUND


def _resolve_ticket(token: str, db: Session) -> tuple[Ticket, Raffle]:
    _validate_token(token)
    row = (
        db.query(Ticket, Raffle)
        .join(Raffle, Ticket.raffle_id == Raffle.id)
        .filter(Ticket.token == token)
        .first()
    )
    if row is None:
        raise _NOT_FOUND
    ticket, raffle = row
    # A deleted raffle's tokens are dead — indistinguishable from unknown.
    if raffle.deleted_at is not None:
        raise _NOT_FOUND
    return ticket, raffle


@router.get("/register/{token}", response_model=RegisterInfoResponse)
def register_info(token: str, db: Session = Depends(get_db)) -> RegisterInfoResponse:
    ticket, raffle = _resolve_ticket(token, db)
    return RegisterInfoResponse(
        ticket_number=ticket.ticket_number,
        raffle_name=raffle.name,
        registered=ticket.registered,
    )


@router.post(
    "/register/{token}",
    response_model=RegisterConfirmation,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(REGISTER_LIMIT)
def register(
    request: Request,
    token: str,
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterConfirmation:
    ticket, raffle = _resolve_ticket(token, db)

    # Registration window is only open while the raffle is active.
    if raffle.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration is closed for this raffle.",
        )
    if ticket.registered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is already registered.",
        )

    entry = Entry(
        ticket_id=ticket.id,
        raffle_id=raffle.id,
        name=body.name,
        email=str(body.email),
    )
    ticket.registered = True
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        # The UNIQUE(ticket_id) constraint fired: a concurrent request
        # registered this ticket first. Surface it as the same 409.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is already registered.",
        )

    return RegisterConfirmation(
        ticket_number=ticket.ticket_number,
        raffle_name=raffle.name,
        name=entry.name,
    )
