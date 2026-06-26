"""Tests for seller-authenticated, ownership-checked ticket registration:
GET /register/{token} and POST /register/{token}. Buyers cannot self-register;
only the org that owns the ticket may register it."""

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db


def _first_token(app_and_db, raffle_id):
    _, database_mod = app_and_db
    db_session = database_mod.SessionLocal()
    try:
        tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
        return tickets[0].token
    finally:
        db_session.close()


def _owned_ticket(client, app_and_db, org, name="Summer Giveaway", count=1):
    raffle_id = create_raffle(client, org["headers"], name)
    generate_tickets(client, org["headers"], raffle_id, count=count)
    return raffle_id, _first_token(app_and_db, raffle_id)


class TestRegisterGet:
    def test_owned_ticket_returns_details(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = client.get(f"/register/{token}", headers=free_org["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["owned"] is True
        assert body["ticket_number"] == 1
        assert body["raffle_name"] == "Summer Giveaway"
        assert body["registered"] is False
        assert "raffle_id" not in body

    def test_other_orgs_ticket_reports_not_owned(
        self, client, app_and_db, free_org, org_b
    ):
        _, token = _owned_ticket(client, app_and_db, free_org)
        # org_b scans a ticket that belongs to free_org.
        resp = client.get(f"/register/{token}", headers=org_b["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["owned"] is False
        # No details about another org's ticket are leaked.
        assert body["ticket_number"] is None
        assert body["raffle_name"] is None

    def test_requires_authentication(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        assert client.get(f"/register/{token}").status_code == 401

    def test_unknown_token_returns_404(self, client, free_org):
        token = "A" * 32  # valid charset/length but not in DB
        resp = client.get(f"/register/{token}", headers=free_org["headers"])
        assert resp.status_code == 404

    def test_malformed_token_too_short_returns_404(self, client, free_org):
        assert (
            client.get("/register/short", headers=free_org["headers"]).status_code
            == 404
        )

    def test_malformed_token_wrong_charset_returns_404(self, client, free_org):
        token = "A" * 31 + "!"
        assert (
            client.get(f"/register/{token}", headers=free_org["headers"]).status_code
            == 404
        )

    def test_malformed_token_too_long_returns_404(self, client, free_org):
        token = "A" * 64
        assert (
            client.get(f"/register/{token}", headers=free_org["headers"]).status_code
            == 404
        )


class TestRegisterPost:
    def _post(self, client, token, headers, name="Alice", email="alice@example.com"):
        return client.post(
            f"/register/{token}", json={"name": name, "email": email}, headers=headers
        )

    def test_creates_entry(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = self._post(client, token, free_org["headers"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["ticket_number"] == 1
        assert body["name"] == "Alice"

    def test_requires_authentication(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = client.post(
            f"/register/{token}", json={"name": "A", "email": "a@b.co"}
        )
        assert resp.status_code == 401

    def test_other_org_cannot_register_returns_403(
        self, client, app_and_db, free_org, org_b
    ):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = self._post(client, token, org_b["headers"])
        assert resp.status_code == 403

    def test_strips_whitespace_from_name(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = self._post(client, token, free_org["headers"], name="  Alice  ")
        assert resp.status_code == 201
        assert resp.json()["name"] == "Alice"

    def test_marks_ticket_registered(self, client, app_and_db, free_org):
        _, database_mod = app_and_db
        raffle_id, token = _owned_ticket(client, app_and_db, free_org)
        self._post(client, token, free_org["headers"])
        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            assert tickets[0].registered is True
        finally:
            db_session.close()

    def test_double_registration_returns_409(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        self._post(client, token, free_org["headers"])
        assert self._post(client, token, free_org["headers"]).status_code == 409

    def test_empty_name_returns_422(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        assert self._post(client, token, free_org["headers"], name="").status_code == 422

    def test_whitespace_name_returns_422(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        assert (
            self._post(client, token, free_org["headers"], name="   ").status_code
            == 422
        )

    def test_invalid_email_returns_422(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        assert (
            self._post(client, token, free_org["headers"], email="nope").status_code
            == 422
        )

    def test_closed_raffle_returns_409(self, client, app_and_db, free_org):
        raffle_id, token = _owned_ticket(client, app_and_db, free_org, count=2)
        client.patch(
            f"/raffles/{raffle_id}",
            json={"status": "closed"},
            headers=free_org["headers"],
        )
        assert self._post(client, token, free_org["headers"]).status_code == 409

    def test_drawn_raffle_returns_409(self, client, app_and_db, free_org):
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=2)
        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            token_0, token_1 = tickets[0].token, tickets[1].token
        finally:
            db_session.close()
        self._post(client, token_0, free_org["headers"])
        client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        assert self._post(client, token_1, free_org["headers"]).status_code == 409

    def test_deleted_raffle_returns_404(self, client, app_and_db, free_org):
        raffle_id, token = _owned_ticket(client, app_and_db, free_org)
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])
        assert (
            client.get(f"/register/{token}", headers=free_org["headers"]).status_code
            == 404
        )

    def test_get_shows_registered_after_post(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        self._post(client, token, free_org["headers"])
        resp = client.get(f"/register/{token}", headers=free_org["headers"])
        assert resp.json()["registered"] is True

    def test_stores_and_returns_phone(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = client.post(
            f"/register/{token}",
            json={
                "name": "Bob",
                "email": "bob@example.com",
                "phone": "+1 5855551234",
            },
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        info = client.get(f"/register/{token}", headers=free_org["headers"]).json()
        assert info["registrant_phone"] == "+1 5855551234"

    def test_invalid_phone_returns_422(self, client, app_and_db, free_org):
        _, token = _owned_ticket(client, app_and_db, free_org)
        resp = client.post(
            f"/register/{token}",
            json={"name": "Bob", "email": "bob@example.com", "phone": "abc"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 422
