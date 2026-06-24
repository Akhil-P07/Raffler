"""Verifiable winner selection.

Uses the OS CSPRNG via `secrets.SystemRandom`, not `random`. The result is
not seedable and cannot be reproduced or predicted, which is the whole point
of a fair draw. We still record a `rng_seed` value on the raffle as an audit
marker for *when/what* was drawn — it is NOT a reproducible seed (that would
defeat unpredictability), but a unique tamper-evident token tying the recorded
result to a single draw event.
"""
import secrets

_sysrand = secrets.SystemRandom()


def select_winners(entry_ids: list[str], prize_count: int) -> list[str]:
    """Pick up to `prize_count` distinct winners from `entry_ids`.

    Returns the winning entry ids in draw order (prize_rank 1, 2, ...).
    """
    if not entry_ids:
        return []

    count = min(prize_count, len(entry_ids))
    # sample() with SystemRandom draws distinct entries without replacement.
    return _sysrand.sample(entry_ids, count)


def audit_token() -> str:
    """A unique, unguessable marker recorded on the raffle at draw time."""
    return secrets.token_urlsafe(24)
