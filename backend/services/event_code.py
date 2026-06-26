"""Per-raffle event codes.

Each raffle gets a short, human-readable code derived from its name plus a
numeric uniquifier (e.g. "Spring Gala" -> "SG01"). It's printed on every ticket
as the serial prefix: #<event_code>-<ticket_number>. Pure functions only (no DB
imports) so both the create path and the startup backfill can reuse them.
"""
import re

_ALNUM = re.compile(r"[A-Za-z0-9]+")


def _base(name: str) -> str:
    """The letter part of the code: word initials for multi-word names, or the
    first few characters for a single word. Falls back to 'RF' for nameless or
    symbol-only names."""
    words = _ALNUM.findall(name or "")
    if not words:
        return "RF"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words[:4]).upper()


def make_event_code(name: str, taken: set[str]) -> str:
    """Return a unique code for `name` not already in `taken` (two-digit min
    suffix, growing as needed): SG01, SG02, ... The caller is responsible for
    adding the result to `taken` before generating the next one."""
    base = _base(name)
    n = 1
    while True:
        code = f"{base}{n:02d}"
        if code not in taken:
            return code
        n += 1
