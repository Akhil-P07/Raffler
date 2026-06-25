"""Entry listing, CSV export, and owner-only deregistration."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Entry, Organization, Ticket, get_db
from middleware.ownership import get_owned_raffle, require_org, require_owner
from schemas import DeregisterRequest, DeregisterResponse, EntryResponse

router = APIRouter(tags=["entries"])

# Spreadsheet formula-injection: a cell beginning with one of these is treated
# as a formula by Excel/Sheets. name/email come from public registration, so
# neutralize them by prefixing a single quote before writing to CSV.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


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


@router.get(
    "/raffles/{raffle_id}/entries/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV download"}},
)
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
        writer.writerow(
            [
                number,
                _csv_safe(entry.name),
                _csv_safe(entry.email),
                entry.registered_at,
            ]
        )

    filename = f"raffle-{raffle.id}-entries.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/raffles/{raffle_id}/entries/deregister",
    response_model=DeregisterResponse,
)
def deregister_entries(
    raffle_id: str,
    body: DeregisterRequest,
    org: Organization = Depends(require_owner),
    db: Session = Depends(get_db),
) -> DeregisterResponse:
    """Owner-only: delete the selected entries and free their tickets so they
    can be registered again (recovery for when something goes wrong). Blocked
    once the raffle is drawn, to protect the recorded result."""
    raffle = get_owned_raffle(raffle_id, org, db)
    if raffle.status == "drawn":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot deregister tickets after the raffle has been drawn.",
        )

    count = 0
    for entry_id in set(body.entry_ids):
        entry = db.get(Entry, entry_id)
        # Only touch entries that belong to this raffle (ownership already
        # confirmed on the raffle).
        if entry is None or entry.raffle_id != raffle.id:
            continue
        ticket = db.get(Ticket, entry.ticket_id)
        if ticket is not None:
            ticket.registered = False
        db.delete(entry)
        count += 1

    db.commit()
    return DeregisterResponse(deregistered=count)
