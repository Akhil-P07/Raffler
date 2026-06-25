"""Session authentication and ownership resolution.

Every protected route depends on `require_org` to authenticate the user's
session (Bearer JWT) and resolve their organization, then uses the
`get_owned_*` helpers to confirm a resource belongs to that org. Ownership
mismatches raise 404 (not 403) so the API never leaks whether a resource id
exists in another org's namespace.

Centralizing this here means no individual route can forget the check.
"""
import uuid
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Entry, Membership, Organization, Raffle, Ticket, get_db
from security import decode_session_token

_INVALID_SESSION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)

_OWNER_ONLY = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required."
)

# Reused for every ownership miss so existence is indistinguishable from
# "belongs to someone else".
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found."
)

_bearer = HTTPBearer(auto_error=False)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def get_session(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """Decode and validate the session Bearer token; return its claims."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise _INVALID_SESSION
    claims = decode_session_token(creds.credentials)
    if claims is None:
        raise _INVALID_SESSION
    return claims


def _current_membership(claims: dict[str, Any], db: Session) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.user_id == claims.get("sub"),
            Membership.org_id == claims.get("org_id"),
        )
    )


def require_org(
    claims: dict[str, Any] = Depends(get_session),
    db: Session = Depends(get_db),
) -> Organization:
    """Resolve the selected org and confirm the session user is still a member
    of it (an owner-removed member's old token stops working immediately)."""
    if _current_membership(claims, db) is None:
        raise _INVALID_SESSION
    org = db.get(Organization, claims.get("org_id"))
    if org is None:
        raise _INVALID_SESSION
    return org


def require_owner(
    claims: dict[str, Any] = Depends(get_session),
    db: Session = Depends(get_db),
) -> Organization:
    """Like require_org but the session user must be an OWNER of the selected
    org. Used for ticket QR/print/generation, member management, and
    deregistration — actions an invited member must not perform."""
    membership = _current_membership(claims, db)
    if membership is None or membership.role != "owner":
        raise _OWNER_ONLY
    org = db.get(Organization, claims.get("org_id"))
    if org is None:
        raise _INVALID_SESSION
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
