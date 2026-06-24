"""FastAPI application entry point.

Wires routers, CORS, security headers, rate limiting, and DB init. Also seeds
the founding RIT AI Club org on the Club plan when the table is empty, printing
its API key once to the server log (only ever happens on a fresh database).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import settings
from database import Organization, SessionLocal, init_db
from middleware.rate_limit import limiter
from middleware.security_headers import SecurityHeadersMiddleware
from routers import auth, draw, entries, raffles, register, tickets
from security import generate_api_key, hash_api_key

logger = logging.getLogger("raffler")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: create tables, flag weak creds, seed the founding org.
    init_db()
    _warn_on_weak_admin()
    _seed_founding_org()
    yield


app = FastAPI(
    title="Raffler API",
    version="1.0.0",
    description="Multi-tenant raffle registration and draw platform.",
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
    allow_headers=["X-API-Key", "Authorization", "Content-Type"],
)

# --- Routers --------------------------------------------------------------
app.include_router(auth.router)
app.include_router(raffles.router)
app.include_router(tickets.router)
app.include_router(register.router)
app.include_router(entries.router)
app.include_router(draw.router)


def _seed_founding_org() -> None:
    """Provision RIT AI Club on the Club plan if no orgs exist yet."""
    db = SessionLocal()
    try:
        if db.query(Organization).first() is not None:
            return
        org = Organization(name="RIT AI Club", plan="club", api_key="pending")
        db.add(org)
        db.flush()
        api_key = generate_api_key(org.id)
        org.api_key = hash_api_key(api_key)
        db.commit()
        logger.warning(
            "Seeded founding org 'RIT AI Club' (id=%s). API key (shown once): %s",
            org.id,
            api_key,
        )
    finally:
        db.close()


def _warn_on_weak_admin() -> None:
    """Loudly flag default/weak admin credentials so they can't quietly reach
    production. Not a hard failure (the SQLite/dev path relies on defaults),
    but unmissable in the logs."""
    if settings.ADMIN_PASSWORD in ("changeme", "", "use-a-long-random-password"):
        logger.warning(
            "ADMIN_PASSWORD is set to a default/example value. Set a strong "
            "ADMIN_PASSWORD env var before exposing this deployment — the admin "
            "login can create orgs and rotate every tenant's API key."
        )


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
