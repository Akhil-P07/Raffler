"""Org authentication and ownership resolution.

Every protected route depends on `require_org` to authenticate the API key,
then uses the `get_owned_*` helpers to resolve a resource and confirm it
belongs to that org. Ownership mismatches raise 404 (not 403) so the API never
leaks whether a resource id exists in another org's namespace.

Centralizing this here means no individual route can forget the check.
"""
import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Entry, Organization, Raffle, Ticket, get_db
from security import parse_org_id, verify_api_key

_INVALID_KEY = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing API key.",
    headers={"WWW-Authenticate": "X-API-Key"},
)

# Reused for every ownership miss so existence is indistinguishable from
# "belongs to someone else".
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found."
)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def require_org(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Organization:
    """Authenticate the X-API-Key header and return the owning Organization."""
    if not x_api_key:
        raise _INVALID_KEY

    org_id = parse_org_id(x_api_key)
    if org_id is None or not _is_uuid(org_id):
        raise _INVALID_KEY

    org = db.get(Organization, org_id)
    if org is None or not verify_api_key(x_api_key, org.api_key):
        raise _INVALID_KEY

    return org


def get_owned_raffle(
    raffle_id: str, org: Organization, db: Session, *, include_deleted: bool = False
) -> Raffle:
    """Resolve a raffle and confirm it belongs to `org`. 404 on any mismatch."""
    if not _is_uuid(raffle_id):
        raise _NOT_FOUND

    raffle = db.get(Raffle, raffle_id)
    if raffle is None or raffle.org_id != org.id:
        raise _NOT_FOUND
    if raffle.deleted_at is not None and not include_deleted:
        raise _NOT_FOUND
    return raffle


def get_owned_ticket(ticket_id: str, org: Organization, db: Session) -> Ticket:
    """Resolve a ticket via ticket → raffle → org. 404 on any mismatch."""
    if not _is_uuid(ticket_id):
        raise _NOT_FOUND

    row = db.execute(
        select(Ticket, Raffle)
        .join(Raffle, Ticket.raffle_id == Raffle.id)
        .where(Ticket.id == ticket_id)
    ).first()
    if row is None:
        raise _NOT_FOUND
    ticket, raffle = row
    if raffle.org_id != org.id or raffle.deleted_at is not None:
        raise _NOT_FOUND
    return ticket


def get_owned_entry(entry_id: str, org: Organization, db: Session) -> Entry:
    """Resolve an entry via entry → raffle → org. 404 on any mismatch."""
    if not _is_uuid(entry_id):
        raise _NOT_FOUND

    row = db.execute(
        select(Entry, Raffle)
        .join(Raffle, Entry.raffle_id == Raffle.id)
        .where(Entry.id == entry_id)
    ).first()
    if row is None:
        raise _NOT_FOUND
    entry, raffle = row
    if raffle.org_id != org.id or raffle.deleted_at is not None:
        raise _NOT_FOUND
    return entry
