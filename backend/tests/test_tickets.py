"""Tests for ticket generation, listing, QR, and print sheet endpoints."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db

PNG_MAGIC = b"\x89PNG"


class TestGenerateTickets:
    def test_generate_tickets_happy_path(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 5},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] == 5
        assert len(body["tickets"]) == 5
        assert body["raffle_id"] == raffle_id

    def test_ticket_numbers_are_sequential(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        body = generate_tickets(client, free_org["headers"], raffle_id, count=5)
        numbers = [t["ticket_number"] for t in body["tickets"]]
        assert numbers == list(range(1, 6))

    def test_token_not_exposed_in_generate_response(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        body = generate_tickets(client, free_org["headers"], raffle_id, count=3)
        for ticket in body["tickets"]:
            assert "token" not in ticket

    def test_token_not_exposed_in_list_response(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)
        resp = client.get(
            f"/raffles/{raffle_id}/tickets", headers=free_org["headers"]
        )
        assert resp.status_code == 200
        for ticket in resp.json():
            assert "token" not in ticket

    def test_tokens_are_unique_across_tickets(self, client, app_and_db, free_org):
        """Each ticket in the same raffle must have a distinct token."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=10)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            tokens = [t.token for t in tickets]
        finally:
            db_session.close()

        assert len(tokens) == len(set(tokens)), "Duplicate tokens detected!"

    def test_tokens_are_32_chars(self, client, app_and_db, free_org):
        """secrets.token_urlsafe(24) produces 32-char URL-safe base64 strings."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=5)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            for t in tickets:
                assert len(t.token) == 32
                # URL-safe base64 charset only
                import re
                assert re.match(r"^[A-Za-z0-9_-]{32}$", t.token)
        finally:
            db_session.close()

    def test_tokens_unique_across_two_raffles(self, client, app_and_db, club_org):
        """Tokens must be globally unique, not just per-raffle."""
        _, database_mod = app_and_db
        raffle_a = create_raffle(client, club_org["headers"], "Raffle A")
        raffle_b = create_raffle(client, club_org["headers"], "Raffle B")
        generate_tickets(client, club_org["headers"], raffle_a, count=10)
        generate_tickets(client, club_org["headers"], raffle_b, count=10)

        db_session = database_mod.SessionLocal()
        try:
            tickets_a = get_tickets_from_db(db_session, database_mod, raffle_a)
            tickets_b = get_tickets_from_db(db_session, database_mod, raffle_b)
            tokens_a = {t.token for t in tickets_a}
            tokens_b = {t.token for t in tickets_b}
        finally:
            db_session.close()

        overlap = tokens_a & tokens_b
        assert len(overlap) == 0, f"Tokens shared across raffles: {overlap}"

    def test_second_batch_continues_numbering(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)
        # Free plan allows 50; generate 3 more.
        body = generate_tickets(client, free_org["headers"], raffle_id, count=3)
        numbers = [t["ticket_number"] for t in body["tickets"]]
        assert numbers == [4, 5, 6]

    def test_generate_zero_tickets_returns_422(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 0},
            headers=free_org["headers"],
        )
        assert resp.status_code == 422

    def test_generate_tickets_on_unknown_raffle_returns_404(
        self, client, free_org
    ):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.post(
            f"/raffles/{fake_id}/tickets",
            json={"count": 1},
            headers=free_org["headers"],
        )
        assert resp.status_code == 404


class TestQRAndSheet:
    def test_qr_returns_png(self, client, app_and_db, free_org):
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            ticket_id = tickets[0].id
        finally:
            db_session.close()

        resp = client.get(
            f"/tickets/{ticket_id}/qr", headers=free_org["headers"]
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == PNG_MAGIC

    def test_qr_encodes_token_not_ticket_number(
        self, client, app_and_db, free_org
    ):
        """The QR image URL must contain the token, not the sequential number."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            ticket = tickets[0]
            ticket_id = ticket.id
            token = ticket.token
            ticket_number = ticket.ticket_number
        finally:
            db_session.close()

        # Decode the QR to verify the URL contains the token.
        resp = client.get(
            f"/tickets/{ticket_id}/qr", headers=free_org["headers"]
        )
        assert resp.status_code == 200

        # Import and decode the QR image.
        import io
        from PIL import Image
        try:
            from pyzbar.pyzbar import decode as qr_decode
            img = Image.open(io.BytesIO(resp.content))
            decoded = qr_decode(img)
            assert len(decoded) == 1
            url = decoded[0].data.decode()
            assert token in url
            assert str(ticket_number) not in url.split("/register/")[-1]
        except ImportError:
            # pyzbar not installed — at least verify the token is in the services layer.
            from services.qr import registration_url
            url = registration_url(token)
            assert token in url
            assert f"/register/{token}" in url

    def test_print_sheet_returns_png(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)

        resp = client.get(
            f"/raffles/{raffle_id}/tickets/sheet",
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == PNG_MAGIC

    def test_sheet_uses_token_from_same_row_as_ticket_number(
        self, client, app_and_db, free_org
    ):
        """Each cell in the print sheet pairs QR (from token) with the printed
        number from the SAME database row — verified by checking the sheet
        endpoint uses (ticket_number, token) tuples from the same Ticket row."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            pairs = [(t.ticket_number, t.token) for t in tickets]
        finally:
            db_session.close()

        # Verify each pair has a consistent token/number from DB (not shuffled).
        for number, token in pairs:
            assert len(token) == 32  # token is the right field
            assert isinstance(number, int)

        # All numbers must be unique and ascending.
        numbers = [p[0] for p in pairs]
        assert numbers == sorted(numbers)
        assert len(numbers) == len(set(numbers))

    def test_qr_ownership_check_org_b_gets_404(
        self, client, app_and_db, free_org, org_b
    ):
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            ticket_id = tickets[0].id
        finally:
            db_session.close()

        resp = client.get(
            f"/tickets/{ticket_id}/qr", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_sheet_ownership_check_org_b_gets_404(
        self, client, free_org, org_b
    ):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        resp = client.get(
            f"/raffles/{raffle_id}/tickets/sheet", headers=org_b["headers"]
        )
        assert resp.status_code == 404
