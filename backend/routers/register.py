"""Ticket registration — performed by the logged-in seller, NOT the buyer.

The seller scans a ticket's QR (which opens /register/{token} in their portal),
the server confirms the ticket belongs to the seller's own organization, and
only then accepts the buyer's name + email. There is no public self-service
registration: that would let anyone with a token register (or hijack) a ticket.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Entry, Organization, Raffle, Ticket, get_db
from middleware.ownership import require_org
from schemas import RegisterConfirmation, RegisterInfoResponse, RegisterRequest

router = APIRouter(tags=["registration"])

# token_urlsafe(24) -> exactly 32 chars from the URL-safe base64 alphabet.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found."
)
_OTHER_ORG = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="This ticket belongs to a different organization.",
)


def _resolve_ticket(token: str, db: Session) -> tuple[Ticket, Raffle]:
    if not _TOKEN_RE.match(token):
        # Same 404 as an unknown token so length/charset can't be probed.
        raise _NOT_FOUND
    row = (
        db.query(Ticket, Raffle)
        .join(Raffle, Ticket.raffle_id == Raffle.id)
        .filter(Ticket.token == token)
        .first()
    )
    if row is None:
        raise _NOT_FOUND
    ticket, raffle = row
    if raffle.deleted_at is not None:
        raise _NOT_FOUND
    return ticket, raffle


@router.get("/register/{token}", response_model=RegisterInfoResponse)
def register_info(
    token: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> RegisterInfoResponse:
    """Resolve a scanned ticket for the logged-in seller. If the ticket isn't
    theirs, report `owned: false` without leaking the ticket/raffle details."""
    ticket, raffle = _resolve_ticket(token, db)
    if raffle.org_id != org.id:
        return RegisterInfoResponse(owned=False)
    return RegisterInfoResponse(
        owned=True,
        ticket_number=ticket.ticket_number,
        raffle_name=raffle.name,
        registered=ticket.registered,
    )


@router.post(
    "/register/{token}",
    response_model=RegisterConfirmation,
    status_code=status.HTTP_201_CREATED,
)
def register(
    token: str,
    body: RegisterRequest,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> RegisterConfirmation:
    ticket, raffle = _resolve_ticket(token, db)

    # Theft prevention: only the org that owns the ticket may register it.
    if raffle.org_id != org.id:
        raise _OTHER_ORG

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
