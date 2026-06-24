"""slowapi rate limiter configuration.

Per-IP limits. Per-route ceilings are declared with the @limiter.limit
decorator on the relevant endpoints:

    POST /auth/login        -> 10/minute   (brute force protection)
    POST /register/{token}  -> 20/minute   (spam registration protection)
    POST /raffles/{id}/draw -> 5/minute    (draw abuse protection)
    everything else         -> 100/minute  (general abuse protection)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
)

# Named limits referenced by routers, kept here so the policy lives in one file.
LOGIN_LIMIT = "10/minute"
REGISTER_LIMIT = "20/minute"
DRAW_LIMIT = "5/minute"
