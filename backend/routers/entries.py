"""Entry listing and CSV export (for offline use / backups)."""
import csv
import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Entry, Organization, Ticket, get_db
from middleware.ownership import get_owned_raffle, require_org
from schemas import EntryResponse

router = APIRouter(tags=["entries"])


def _entries_with_numbers(db: Session, raffle_id: str) -> list[tuple[Entry, int]]:
    rows = db.execute(
        select(Entry, Ticket.ticket_number)
        .join(Ticket, Entry.ticket_id == Ticket.id)
        .where(Entry.raffle_id == raffle_id)
        .order_by(Ticket.ticket_number)
    ).all()
    return [(entry, number) for entry, number in rows]


@router.get("/raffles/{raffle_id}/entries", response_model=list[EntryResponse])
def list_entries(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> list[EntryResponse]:
    raffle = get_owned_raffle(raffle_id, org, db)
    return [
        EntryResponse(
            id=entry.id,
            name=entry.name,
            email=entry.email,
            ticket_number=number,
            registered_at=entry.registered_at,
        )
        for entry, number in _entries_with_numbers(db, raffle.id)
    ]


@router.get("/raffles/{raffle_id}/entries/export")
def export_entries(
    raffle_id: str,
    org: Organization = Depends(require_org),
    db: Session = Depends(get_db),
) -> Response:
    raffle = get_owned_raffle(raffle_id, org, db)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ticket_number", "name", "email", "registered_at"])
    for entry, number in _entries_with_numbers(db, raffle.id):
        writer.writerow([number, entry.name, entry.email, entry.registered_at])

    filename = f"raffle-{raffle.id}-entries.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
