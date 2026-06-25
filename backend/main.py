"""FastAPI application entry point.

Wires routers, CORS, security headers, rate limiting, and DB init. Auth is
session-based (Google or email/password self-signup); there are no API keys.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import settings
from database import init_db
from middleware.rate_limit import limiter
from middleware.security_headers import SecurityHeadersMiddleware
from routers import auth, draw, entries, logos, raffles, register, tickets

logger = logging.getLogger("raffler")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: create tables, flag weak admin credentials.
    init_db()
    _warn_on_weak_admin()
    yield


app = FastAPI(
    title="Raffler API",
    version="2.0.0",
    description="Raffle registration and draw platform with email/Google login.",
    lifespan=lifespan,
)

# --- Rate limiting --------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Security headers (added before CORS so CORS runs outermost) ----------
app.add_middleware(SecurityHeadersMiddleware)

# --- CORS: exact frontend origin, never "*" -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# --- Routers --------------------------------------------------------------
app.include_router(auth.router)
app.include_router(raffles.router)
app.include_router(tickets.router)
app.include_router(register.router)
app.include_router(entries.router)
app.include_router(draw.router)
app.include_router(logos.router)


def _warn_on_weak_admin() -> None:
    """Loudly flag default/weak admin credentials so they can't quietly reach
    production. Not a hard failure (the SQLite/dev path relies on defaults),
    but unmissable in the logs."""
    if settings.ADMIN_PASSWORD in ("changeme", "", "use-a-long-random-password"):
        logger.warning(
            "ADMIN_PASSWORD is set to a default/example value. Set a strong "
            "ADMIN_PASSWORD env var before exposing this deployment — the admin "
            "login manages the premium allowlist."
        )


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
