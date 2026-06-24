"""Plan limit enforcement.

| Plan | Active raffles | Tickets per raffle |
|------|----------------|--------------------|
| Free | 1              | 50                 |
| Club | unlimited      | unlimited          |

"Active" means status != 'drawn' AND deleted_at IS NULL. Over-limit requests
raise an HTTP 403 with a clear message (the spec mandates 403, not 422, for
plan ceilings).
"""
from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from database import Organization, Raffle, Ticket

# None means "unlimited".
PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free": {"active_raffles": 1, "tickets_per_raffle": 50},
    "club": {"active_raffles": None, "tickets_per_raffle": None},
}


def _limits_for(plan: str) -> dict[str, int | None]:
    # Unknown plans fall back to the most restrictive tier.
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def _lock_org(db: Session, org_id: str) -> None:
    """Row-lock the org so the count-then-insert that follows is serialized.
    Without this, two concurrent creates from the same org both read a count
    under the limit and both commit, overshooting the ceiling. The lock is
    held until the request commits. (No-op on SQLite, which serializes writes
    anyway.)"""
    db.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )


def enforce_active_raffle_limit(db: Session, org_id: str, plan: str) -> None:
    limit = _limits_for(plan)["active_raffles"]
    if limit is None:
        return

    _lock_org(db, org_id)
    active_count = db.scalar(
        select(func.count())
        .select_from(Raffle)
        .where(
            and_(
                Raffle.org_id == org_id,
                Raffle.status != "drawn",
                Raffle.deleted_at.is_(None),
            )
        )
    )
    if active_count is not None and active_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plan limit reached: the {plan} plan allows {limit} active "
                "raffle(s). Upgrade to the Club plan for unlimited raffles."
            ),
        )


def enforce_ticket_limit(
    db: Session, raffle_id: str, plan: str, requested: int
) -> None:
    limit = _limits_for(plan)["tickets_per_raffle"]
    if limit is None:
        return

    # Lock the raffle row so two concurrent generate calls can't both pass the
    # count and overshoot the per-raffle cap.
    db.execute(select(Raffle.id).where(Raffle.id == raffle_id).with_for_update())
    existing = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.raffle_id == raffle_id)
    ) or 0

    if existing + requested > limit:
        remaining = max(limit - existing, 0)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plan limit reached: the {plan} plan allows {limit} tickets "
                f"per raffle ({existing} already generated, {remaining} "
                "remaining). Upgrade to the Club plan for unlimited tickets."
            ),
        )
