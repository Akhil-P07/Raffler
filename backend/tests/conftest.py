"""
Shared fixtures for the Raffler test suite.

Isolation strategy
------------------
Each test gets a fresh SQLite file via a function-scoped fixture.  Because
database.py reads DATABASE_URL *at import time* and config uses an lru_cache,
we patch os.environ *before* the first import, then importlib.reload the
relevant modules for every test so the in-memory state is clean.

The TestClient is instantiated *without* using it as a context manager, so
FastAPI's on_startup event does NOT fire automatically.  We call
database.init_db() directly to create tables.
"""
import importlib
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Module-level sentinel so we set env vars once before any import.
# ---------------------------------------------------------------------------
_MODULES_TO_RELOAD = [
    "config",
    "database",
    "security",
    "middleware.ownership",
    "middleware.rate_limit",
    "middleware.security_headers",
    "services.limits",
    "services.qr",
    "services.rng",
    "routers.auth",
    "routers.raffles",
    "routers.tickets",
    "routers.register",
    "routers.entries",
    "routers.draw",
    "main",
]


def _reload_app(db_path: str):
    """Set env vars, reload all app modules, return (app, database module)."""
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "x" * 40
    os.environ["ADMIN_EMAIL"] = "admin@example.com"
    os.environ["ADMIN_PASSWORD"] = "changeme"
    os.environ["BASE_URL"] = "http://testserver"
    os.environ["FRONTEND_ORIGIN"] = "http://testserver"
    os.environ["API_ORIGIN"] = "http://testserver"

    # Clear the lru_cache on config so the new env vars are picked up.
    for mod_name in _MODULES_TO_RELOAD:
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    # Re-import in dependency order.
    config_mod = importlib.import_module("config")
    config_mod.get_settings.cache_clear()

    for mod_name in _MODULES_TO_RELOAD:
        if mod_name not in sys.modules:
            importlib.import_module(mod_name)

    database_mod = sys.modules["database"]
    main_mod = sys.modules["main"]

    return main_mod.app, database_mod


@pytest.fixture()
def app_and_db():
    """Function-scoped: fresh SQLite DB + reloaded app per test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    app, database_mod = _reload_app(db_path)
    database_mod.init_db()

    yield app, database_mod

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture()
def client(app_and_db):
    """TestClient bound to the freshly loaded app."""
    app, _ = app_and_db
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def db(app_and_db):
    """A direct SQLAlchemy session for DB inspection in tests."""
    _, database_mod = app_and_db
    session = database_mod.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def admin_token(client):
    """JWT for the bootstrap admin."""
    resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "changeme"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Org helpers
# ---------------------------------------------------------------------------

def create_org(client, admin_headers, name="Test Org", plan="free"):
    resp = client.post(
        "/orgs",
        json={"name": name, "plan": plan},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["id"], data["api_key"]


@pytest.fixture()
def free_org(client, admin_headers):
    org_id, api_key = create_org(client, admin_headers, name="Free Org", plan="free")
    return {"id": org_id, "api_key": api_key, "headers": {"X-API-Key": api_key}}


@pytest.fixture()
def club_org(client, admin_headers):
    org_id, api_key = create_org(client, admin_headers, name="Club Org", plan="club")
    return {"id": org_id, "api_key": api_key, "headers": {"X-API-Key": api_key}}


@pytest.fixture()
def org_b(client, admin_headers):
    """A second org, used for isolation tests."""
    org_id, api_key = create_org(client, admin_headers, name="Org B", plan="club")
    return {"id": org_id, "api_key": api_key, "headers": {"X-API-Key": api_key}}


# ---------------------------------------------------------------------------
# Raffle + ticket helpers
# ---------------------------------------------------------------------------

def create_raffle(client, org_headers, name="Test Raffle"):
    resp = client.post("/raffles", json={"name": name}, headers=org_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def generate_tickets(client, org_headers, raffle_id, count=5):
    resp = client.post(
        f"/raffles/{raffle_id}/tickets",
        json={"count": count},
        headers=org_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_tickets_from_db(db_session, database_mod, raffle_id):
    """Read ticket rows directly — tokens are NOT in API responses."""
    tickets = (
        db_session.query(database_mod.Ticket)
        .filter(database_mod.Ticket.raffle_id == raffle_id)
        .order_by(database_mod.Ticket.ticket_number)
        .all()
    )
    return tickets


def register_ticket(client, token, name="Alice", email="alice@example.com"):
    resp = client.post(
        f"/register/{token}",
        json={"name": name, "email": email},
    )
    return resp
