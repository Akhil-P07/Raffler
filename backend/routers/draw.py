"""Verifiable, idempotent winner draw.

Integrity guarantees:
  * A raffle is drawn exactly once. Re-calling returns the recorded winners
    and never re-runs the RNG.
  * Winner selection uses `secrets.SystemRandom` (see services/rng.py) — not
    seedable, not predictable.
  * The raffle row is locked with SELECT ... FOR UPDATE for the duration of
    the transaction, so two concurrent draw requests can't both proceed.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Entry, Organization, Raffle, Ticket, Winner, get_db
from middleware.ownership import get_owned_raffle, require_org
from middleware.rate_limit import DRAW_LIMIT, limiter
from schemas import DrawRequest, DrawResponse, WinnerResponse
from services.rng import audit_token, select_winners

router = APIRouter(tags=["draw"])


def _winner_rows(db: Session, raffle_id: str) -> list[WinnerResponse]:
    rows = db.execute(
        select(Winner, Entry, Ticket.ticket_number)
        .join(Entry, Winner.entry_id == Entry.id)
        .join(Ticket, Entry.ticket_id == Ticket.id)
        .where(Winner.raffle_id == raffle_id)
        .order_by(Winner.prize_rank)
    ).all()
    return [
        WinnerResponse(
            id=winner.id,
            prize_rank=winner.prize_rank,
            name=entry.name,
            email=entry.email,
            ticket_number=number,
            drawn_at=winner.drawn_at,
        )
        for winner, entry, number in rows
    ]


@router.post("/raffles/{raffle_id}/draw", response_model=DrawResponse)
@limiter.limit(DRAW_LIMIT)
def draw(
    request: Request,
    raffle_id: str,
    body: DrawRequest | None = None,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> DrawResponse:
    # Ownership first (404 on miss), then re-load the row under a lock so a
    # concurrent draw blocks here until we commit.
    raffle = get_owned_raffle(raffle_id, org, db)
    raffle = db.execute(
        select(Raffle).where(Raffle.id == raffle.id).with_for_update()
    ).scalar_one()

    # Idempotent: already drawn -> return recorded winners, never re-run.
    if raffle.status == "drawn":
        return DrawResponse(
            raffle_id=raffle.id,
            status=raffle.status,
            already_drawn=True,
            winners=_winner_rows(db, raffle.id),
        )

    entry_ids = list(
        db.scalars(
            select(Entry.id).where(Entry.raffle_id == raffle.id)
        ).all()
    )
    if not entry_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot draw a raffle with no entries.",
        )

    prize_count = body.prize_count if body is not None else 1
    winning_ids = select_winners(entry_ids, prize_count)

    for rank, entry_id in enumerate(winning_ids, start=1):
        db.add(Winner(raffle_id=raffle.id, entry_id=entry_id, prize_rank=rank))

    # Record audit fields on the raffle; set exactly once.
    raffle.status = "drawn"
    raffle.rng_seed = audit_token()
    raffle.drawn_at = datetime.now(timezone.utc)

    db.commit()

    return DrawResponse(
        raffle_id=raffle.id,
        status="drawn",
        already_drawn=False,
        winners=_winner_rows(db, raffle.id),
    )


@router.get("/raffles/{raffle_id}/winners", response_model=list[WinnerResponse])
def list_winners(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[WinnerResponse]:
    raffle = get_owned_raffle(raffle_id, org, db)
    return _winner_rows(db, raffle.id)
