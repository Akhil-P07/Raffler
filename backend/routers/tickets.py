"""Ticket generation, listing, QR codes, and the printable sheet.

Tokens are 32-char `secrets.token_urlsafe` strings carried in the QR URL. The
printed ticket_number is human-only and never appears in a registration link.
"""
import secrets

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Organization, RaffleLogo, Ticket, get_db
from middleware.ownership import get_owned_raffle, get_owned_ticket, require_org
from schemas import (
    GenerateTicketsRequest,
    GenerateTicketsResponse,
    TicketResponse,
)
from services.limits import enforce_ticket_limit
from services.qr import TicketSheetInfo, print_sheet_png, single_ticket_png

router = APIRouter(tags=["tickets"])

TOKEN_BYTES = 24  # token_urlsafe(24) -> 32-char URL-safe string


@router.post(
    "/raffles/{raffle_id}/tickets",
    response_model=GenerateTicketsResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_tickets(
    raffle_id: str,
    body: GenerateTicketsRequest,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> GenerateTicketsResponse:
    raffle = get_owned_raffle(raffle_id, org, db)
    enforce_ticket_limit(db, raffle.id, org.plan, body.count)

    # Continue numbering after any tickets already generated for this raffle.
    current_max = db.scalar(
        select(func.coalesce(func.max(Ticket.ticket_number), 0)).where(
            Ticket.raffle_id == raffle.id
        )
    ) or 0

    new_tickets: list[Ticket] = []
    for offset in range(1, body.count + 1):
        ticket = Ticket(
            raffle_id=raffle.id,
            ticket_number=current_max + offset,
            token=secrets.token_urlsafe(TOKEN_BYTES),
        )
        db.add(ticket)
        new_tickets.append(ticket)

    db.commit()
    for t in new_tickets:
        db.refresh(t)

    return GenerateTicketsResponse(
        raffle_id=raffle.id,
        created=len(new_tickets),
        tickets=[TicketResponse.model_validate(t) for t in new_tickets],
    )


@router.get("/raffles/{raffle_id}/tickets", response_model=list[TicketResponse])
def list_tickets(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[TicketResponse]:
    raffle = get_owned_raffle(raffle_id, org, db)
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.raffle_id == raffle.id)
        .order_by(Ticket.ticket_number)
    ).all()
    return [TicketResponse.model_validate(t) for t in tickets]


@router.get(
    "/raffles/{raffle_id}/tickets/sheet",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Print sheet PNG"}},
)
def ticket_sheet(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> Response:
    raffle = get_owned_raffle(raffle_id, org, db)
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.raffle_id == raffle.id)
        .order_by(Ticket.ticket_number)
    ).all()
    logos = db.scalars(
        select(RaffleLogo)
        .where(RaffleLogo.raffle_id == raffle.id)
        .order_by(RaffleLogo.position)
    ).all()
    info = TicketSheetInfo(
        org_name=org.name,
        raffle_name=raffle.name,
        goc_id=org.goc_id,
        prizes=raffle.prizes,
        ticket_price=raffle.ticket_price,
        drawing_datetime=raffle.drawing_datetime,
        drawing_location=raffle.drawing_location,
        logos=[logo.image for logo in logos],
    )
    png = print_sheet_png([(t.ticket_number, t.token) for t in tickets], info)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'inline; filename="raffle-{raffle.id}-sheet.png"'
            )
        },
    )


@router.get(
    "/tickets/{ticket_id}/qr",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Ticket QR PNG"}},
)
def ticket_qr(
    ticket_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> Response:
    ticket = get_owned_ticket(ticket_id, org, db)
    png = single_ticket_png(ticket.token)
    return Response(content=png, media_type="image/png")
