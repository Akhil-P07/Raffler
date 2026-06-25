"""Raffle CRUD.

Viewing (list/detail) is open to any org member; creating, editing, and
deleting raffles are owner-only — an invited seller-member can register tickets
but must not be able to reshape or remove the org's raffles.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from database import Entry, Organization, Raffle, Ticket, get_db
from middleware.ownership import get_owned_raffle, require_org, require_owner
from schemas import (
    CreateRaffleRequest,
    RaffleDetailResponse,
    RaffleResponse,
    UpdateRaffleRequest,
)
from services.limits import enforce_active_raffle_limit

router = APIRouter(tags=["raffles"])


@router.post(
    "/raffles", response_model=RaffleResponse, status_code=status.HTTP_201_CREATED
)
def create_raffle(
    body: CreateRaffleRequest,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> RaffleResponse:
    enforce_active_raffle_limit(db, org.id, org.plan)
    raffle = Raffle(
        org_id=org.id,
        name=body.name,
        ticket_price=body.ticket_price,
        prizes=body.prizes,
        drawing_datetime=body.drawing_datetime,
        drawing_location=body.drawing_location,
    )
    db.add(raffle)
    db.commit()
    db.refresh(raffle)
    return RaffleResponse.model_validate(raffle)


@router.get("/raffles", response_model=list[RaffleResponse])
def list_raffles(
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[RaffleResponse]:
    raffles = db.scalars(
        select(Raffle)
        .where(and_(Raffle.org_id == org.id, Raffle.deleted_at.is_(None)))
        .order_by(Raffle.created_at.desc())
    ).all()
    return [RaffleResponse.model_validate(r) for r in raffles]


@router.get("/raffles/{raffle_id}", response_model=RaffleDetailResponse)
def get_raffle(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> RaffleDetailResponse:
    raffle = get_owned_raffle(raffle_id, org, db)
    entry_count = db.scalar(
        select(func.count()).select_from(Entry).where(Entry.raffle_id == raffle.id)
    ) or 0
    ticket_count = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.raffle_id == raffle.id)
    ) or 0
    base = RaffleResponse.model_validate(raffle)
    return RaffleDetailResponse(
        **base.model_dump(),
        entry_count=entry_count,
        ticket_count=ticket_count,
    )


@router.patch("/raffles/{raffle_id}", response_model=RaffleResponse)
def update_raffle(
    raffle_id: str,
    body: UpdateRaffleRequest,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> RaffleResponse:
    raffle = get_owned_raffle(raffle_id, org, db)
    # A drawn raffle is final — its name/status are locked.
    if raffle.status == "drawn":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Raffle has been drawn and can no longer be modified.",
        )
    if body.name is not None:
        raffle.name = body.name
    if body.status is not None:
        raffle.status = body.status
    # Use the explicitly-provided set so a field can be cleared (set to null)
    # vs. simply left untouched.
    provided = body.model_fields_set
    for fld in ("ticket_price", "prizes", "drawing_datetime", "drawing_location"):
        if fld in provided:
            setattr(raffle, fld, getattr(body, fld))
    db.commit()
    db.refresh(raffle)
    return RaffleResponse.model_validate(raffle)


@router.delete("/raffles/{raffle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_raffle(
    raffle_id: str,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    raffle = get_owned_raffle(raffle_id, org, db)
    # Soft delete — a misclick must never wipe an event's entries.
    if raffle.deleted_at is None:
        raffle.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return None
