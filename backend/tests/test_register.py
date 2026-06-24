"""Tests for public registration: GET /register/{token} and POST /register/{token}."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db


def _get_first_token(client, app_and_db, org_headers, raffle_id):
    _, database_mod = app_and_db
    db_session = database_mod.SessionLocal()
    try:
        tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
        return tickets[0].token
    finally:
        db_session.close()


class TestRegisterGet:
    def test_get_register_info_returns_ticket_number_and_raffle_name(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"], "Summer Giveaway")
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.get(f"/register/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticket_number"] == 1
        assert body["raffle_name"] == "Summer Giveaway"
        assert body["registered"] is False

    def test_get_register_does_not_expose_raffle_id(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.get(f"/register/{token}")
        body = resp.json()
        assert "raffle_id" not in body

    def test_unknown_token_returns_404(self, client):
        token = "A" * 32  # valid charset and length, but not in DB
        resp = client.get(f"/register/{token}")
        assert resp.status_code == 404

    def test_malformed_token_too_short_returns_404(self, client):
        resp = client.get("/register/short")
        assert resp.status_code == 404

    def test_malformed_token_wrong_charset_returns_404(self, client):
        # contains space — not in URL-safe base64
        token = "A" * 31 + "!"
        resp = client.get(f"/register/{token}")
        assert resp.status_code == 404

    def test_malformed_token_too_long_returns_404(self, client):
        token = "A" * 64
        resp = client.get(f"/register/{token}")
        assert resp.status_code == 404


class TestRegisterPost:
    def test_register_creates_entry(self, client, app_and_db, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["ticket_number"] == 1
        assert body["name"] == "Alice"
        assert body["message"] == "Registration successful. Good luck!"

    def test_register_strips_whitespace_from_name(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.post(
            f"/register/{token}",
            json={"name": "  Alice  ", "email": "alice@example.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Alice"

    def test_register_marks_ticket_as_registered(
        self, client, app_and_db, free_org
    ):
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        # Confirm registered flag toggled in DB.
        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            assert tickets[0].registered is True
        finally:
            db_session.close()

    def test_double_registration_returns_409(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        resp = client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 409

    def test_register_empty_name_returns_422(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.post(
            f"/register/{token}",
            json={"name": "", "email": "alice@example.com"},
        )
        assert resp.status_code == 422

    def test_register_whitespace_only_name_returns_422(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.post(
            f"/register/{token}",
            json={"name": "   ", "email": "alice@example.com"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email_returns_422(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        resp = client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "not-an-email"},
        )
        assert resp.status_code == 422

    def test_register_on_closed_raffle_returns_409(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=2)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        # Close the raffle.
        client.patch(
            f"/raffles/{raffle_id}",
            json={"status": "closed"},
            headers=free_org["headers"],
        )
        resp = client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 409

    def test_register_on_drawn_raffle_returns_409(
        self, client, app_and_db, free_org
    ):
        """After a draw, the raffle status is 'drawn', blocking registration."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=2)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            token_0 = tickets[0].token
            token_1 = tickets[1].token
        finally:
            db_session.close()

        # Register ticket 0 and draw.
        client.post(
            f"/register/{token_0}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        # Try to register ticket 1 — should fail since raffle is drawn.
        resp = client.post(
            f"/register/{token_1}",
            json={"name": "Bob", "email": "bob@example.com"},
        )
        assert resp.status_code == 409

    def test_register_on_deleted_raffle_returns_404(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])

        resp = client.get(f"/register/{token}")
        assert resp.status_code == 404

    def test_get_shows_registered_true_after_registration(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        token = _get_first_token(client, app_and_db, free_org["headers"], raffle_id)

        client.post(
            f"/register/{token}",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        resp = client.get(f"/register/{token}")
        assert resp.status_code == 200
        assert resp.json()["registered"] is True
