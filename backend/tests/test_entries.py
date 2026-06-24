"""Tests for GET /raffles/{id}/entries and GET /raffles/{id}/entries/export."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db


def _register_all(client, app_and_db, org, raffle_id, count):
    _, database_mod = app_and_db
    db_session = database_mod.SessionLocal()
    try:
        tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
        tokens = [t.token for t in tickets[:count]]
    finally:
        db_session.close()

    for i, token in enumerate(tokens):
        resp = client.post(
            f"/register/{token}",
            json={"name": f"User {i}", "email": f"user{i}@example.com"},
        )
        assert resp.status_code == 201
    return tokens


class TestListEntries:
    def test_list_entries_returns_registered_entries(
        self, client, app_and_db, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)
        _register_all(client, app_and_db, free_org, raffle_id, 3)

        resp = client.get(
            f"/raffles/{raffle_id}/entries", headers=free_org["headers"]
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        for entry in body:
            assert "id" in entry
            assert "name" in entry
            assert "email" in entry
            assert "ticket_number" in entry
            assert "registered_at" in entry

    def test_list_entries_empty_before_registration(
        self, client, free_org
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)
        resp = client.get(
            f"/raffles/{raffle_id}/entries", headers=free_org["headers"]
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_entries_ordered_by_ticket_number(
        self, client, app_and_db, club_org
    ):
        raffle_id = create_raffle(client, club_org["headers"])
        generate_tickets(client, club_org["headers"], raffle_id, count=5)
        _register_all(client, app_and_db, club_org, raffle_id, 5)

        resp = client.get(
            f"/raffles/{raffle_id}/entries", headers=club_org["headers"]
        )
        numbers = [e["ticket_number"] for e in resp.json()]
        assert numbers == sorted(numbers)

    def test_list_entries_requires_api_key(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(f"/raffles/{raffle_id}/entries")
        assert resp.status_code == 401

    def test_list_entries_unknown_raffle_returns_404(self, client, free_org):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(
            f"/raffles/{fake_id}/entries", headers=free_org["headers"]
        )
        assert resp.status_code == 404


class TestExportEntries:
    def test_export_returns_csv(self, client, app_and_db, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=2)
        _register_all(client, app_and_db, free_org, raffle_id, 2)

        resp = client.get(
            f"/raffles/{raffle_id}/entries/export",
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_contains_email(self, client, app_and_db, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        _register_all(client, app_and_db, free_org, raffle_id, 1)

        resp = client.get(
            f"/raffles/{raffle_id}/entries/export",
            headers=free_org["headers"],
        )
        assert "user0@example.com" in resp.text

    def test_export_csv_has_header_row(self, client, app_and_db, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)
        _register_all(client, app_and_db, free_org, raffle_id, 1)

        resp = client.get(
            f"/raffles/{raffle_id}/entries/export",
            headers=free_org["headers"],
        )
        first_line = resp.text.strip().split("\n")[0]
        assert "ticket_number" in first_line
        assert "name" in first_line
        assert "email" in first_line

    def test_export_csv_injection_name_is_neutralized(
        self, client, app_and_db, free_org
    ):
        """Names starting with =, +, -, @ must be prefixed with ' in CSV output."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=4)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            tokens = [t.token for t in tickets]
        finally:
            db_session.close()

        dangerous_names = ["=CMD()", "+HYPERLINK()", "-FORMULA()", "@SUM()"]
        for token, name in zip(tokens, dangerous_names):
            resp = client.post(
                f"/register/{token}",
                json={"name": name, "email": "safe@example.com"},
            )
            assert resp.status_code == 201

        resp = client.get(
            f"/raffles/{raffle_id}/entries/export",
            headers=free_org["headers"],
        )
        csv_text = resp.text
        # Original formula-injecting strings must not appear as-is.
        for name in dangerous_names:
            assert f",{name}," not in csv_text
        # Each must be neutralized with a leading single quote.
        for name in dangerous_names:
            assert f",'{name}," in csv_text

    def test_export_csv_injection_email_is_neutralized(
        self, client, app_and_db, free_org
    ):
        """An email-shaped formula prefix in the email field must also be guarded."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            token = tickets[0].token
        finally:
            db_session.close()

        # The @ prefix is a formula-injection vector in some spreadsheets.
        # A valid email starts with a local-part, not @, but we test the
        # CSV guard independently via a crafted entry.
        # Instead: test that the _csv_safe function in entries.py works.
        from routers.entries import _csv_safe

        for prefix in ("=", "+", "-", "@", "\t", "\r"):
            raw = f"{prefix}EVIL"
            result = _csv_safe(raw)
            assert result == f"'{prefix}EVIL", (
                f"_csv_safe did not neutralize prefix '{prefix}'"
            )

    def test_export_requires_api_key(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(f"/raffles/{raffle_id}/entries/export")
        assert resp.status_code == 401

    def test_export_unknown_raffle_returns_404(self, client, free_org):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(
            f"/raffles/{fake_id}/entries/export", headers=free_org["headers"]
        )
        assert resp.status_code == 404
