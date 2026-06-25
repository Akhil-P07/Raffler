"""Tests for cross-org access controls (org isolation).

Org B must get 404 (not 403) for all of org A's resources.
"""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db, register_ticket


def _full_setup(client, app_and_db, org):
    """Create raffle, tickets, register one entry, return raffle_id and ticket_id."""
    _, database_mod = app_and_db
    raffle_id = create_raffle(client, org["headers"])
    generate_tickets(client, org["headers"], raffle_id, count=2)

    db_session = database_mod.SessionLocal()
    try:
        tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
        ticket_id = tickets[0].id
        token = tickets[0].token
    finally:
        db_session.close()

    register_ticket(client, token, org["headers"])
    return raffle_id, ticket_id


class TestOrgIsolation:
    def test_org_b_cannot_get_org_a_raffle(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_patch_org_a_raffle(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"name": "Hacked"},
            headers=org_b["headers"],
        )
        assert resp.status_code == 404

    def test_org_b_cannot_delete_org_a_raffle(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.delete(
            f"/raffles/{raffle_id}", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_list_org_a_tickets(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}/tickets", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_generate_tickets_for_org_a_raffle(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 1},
            headers=org_b["headers"],
        )
        assert resp.status_code == 404

    def test_org_b_cannot_get_org_a_qr(
        self, client, app_and_db, free_org, org_b
    ):
        _, ticket_id = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/tickets/{ticket_id}/qr", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_get_org_a_sheet(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}/tickets/sheet", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_list_org_a_entries(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}/entries", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_export_org_a_entries(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}/entries/export", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_org_b_cannot_draw_org_a_raffle(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        resp = client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=org_b["headers"],
        )
        assert resp.status_code == 404

    def test_org_b_cannot_list_org_a_winners(
        self, client, app_and_db, free_org, org_b
    ):
        raffle_id, _ = _full_setup(client, app_and_db, free_org)
        # Draw first with org_a.
        client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        resp = client.get(
            f"/raffles/{raffle_id}/winners", headers=org_b["headers"]
        )
        assert resp.status_code == 404

    def test_missing_api_key_returns_401(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(f"/raffles/{raffle_id}")
        assert resp.status_code == 401

    def test_malformed_api_key_returns_401(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(
            f"/raffles/{raffle_id}", headers={"X-API-Key": "notakey"}
        )
        assert resp.status_code == 401

    def test_wrong_secret_in_api_key_returns_401(self, client, free_org):
        """Key with correct org_id but wrong secret must be rejected."""
        org_id = free_org["id"]
        fake_key = f"rk_{org_id}.{'x' * 44}"
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.get(
            f"/raffles/{raffle_id}", headers={"X-API-Key": fake_key}
        )
        assert resp.status_code == 401

    def test_unknown_raffle_id_returns_404(self, client, free_org):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/raffles/{fake_id}", headers=free_org["headers"])
        assert resp.status_code == 404

    def test_malformed_raffle_id_returns_404(self, client, free_org):
        resp = client.get(
            "/raffles/not-a-uuid-at-all", headers=free_org["headers"]
        )
        assert resp.status_code == 404
