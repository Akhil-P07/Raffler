"""Tests for raffle CRUD: POST/GET/PATCH/DELETE /raffles and /raffles/{id}."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db, register_ticket


class TestCreateRaffle:
    def test_create_raffle_happy_path(self, client, free_org):
        resp = client.post(
            "/raffles",
            json={"name": "Spring Raffle"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Spring Raffle"
        assert body["status"] == "active"
        assert body["drawn_at"] is None
        assert "id" in body

    def test_create_raffle_requires_api_key(self, client):
        resp = client.post("/raffles", json={"name": "No Key"})
        assert resp.status_code == 401

    def test_create_raffle_with_invalid_api_key_returns_401(self, client):
        resp = client.post(
            "/raffles",
            json={"name": "Bad Key"},
            headers={"X-API-Key": "rk_bad.key"},
        )
        assert resp.status_code == 401

    def test_create_raffle_with_missing_name_returns_422(self, client, free_org):
        resp = client.post("/raffles", json={}, headers=free_org["headers"])
        assert resp.status_code == 422

    def test_create_raffle_with_whitespace_only_name_returns_422(
        self, client, free_org
    ):
        resp = client.post(
            "/raffles", json={"name": "   "}, headers=free_org["headers"]
        )
        assert resp.status_code == 422


class TestListRaffles:
    def test_list_raffles_returns_only_own_raffles(
        self, client, free_org, org_b
    ):
        create_raffle(client, free_org["headers"], "Raffle A")
        create_raffle(client, org_b["headers"], "Raffle B")

        resp = client.get("/raffles", headers=free_org["headers"])
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert "Raffle A" in names
        assert "Raffle B" not in names

    def test_list_raffles_excludes_deleted(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"], "Deleted Raffle")
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])

        resp = client.get("/raffles", headers=free_org["headers"])
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert raffle_id not in ids


class TestGetRaffle:
    def test_get_raffle_returns_detail(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"], "Detail Raffle")
        resp = client.get(f"/raffles/{raffle_id}", headers=free_org["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == raffle_id
        assert body["entry_count"] == 0
        assert body["ticket_count"] == 0

    def test_get_raffle_unknown_id_returns_404(self, client, free_org):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/raffles/{fake_id}", headers=free_org["headers"])
        assert resp.status_code == 404

    def test_get_raffle_malformed_id_returns_404(self, client, free_org):
        resp = client.get("/raffles/not-a-uuid", headers=free_org["headers"])
        assert resp.status_code == 404


class TestUpdateRaffle:
    def test_patch_raffle_name(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"], "Old Name")
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"name": "New Name"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_patch_raffle_status_to_closed(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"status": "closed"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"

    def test_patch_drawn_raffle_returns_409(
        self, client, app_and_db, free_org
    ):
        """A drawn raffle must not be patchable."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        # Register the ticket via DB token.
        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            token = tickets[0].token
        finally:
            db_session.close()

        register_ticket(client, token)
        client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )

        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"name": "After draw"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 409

    def test_patch_raffle_status_drawn_via_body_is_rejected(
        self, client, free_org
    ):
        """Setting status=drawn through PATCH must be rejected (422)."""
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.patch(
            f"/raffles/{raffle_id}",
            json={"status": "drawn"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 422


class TestDeleteRaffle:
    def test_delete_raffle_returns_204(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.delete(
            f"/raffles/{raffle_id}", headers=free_org["headers"]
        )
        assert resp.status_code == 204

    def test_delete_sets_deleted_at_in_db(self, client, app_and_db, free_org):
        """Soft delete: deleted_at is set but the row is not destroyed."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])

        db_session = database_mod.SessionLocal()
        try:
            raffle = db_session.get(database_mod.Raffle, raffle_id)
            assert raffle is not None
            assert raffle.deleted_at is not None  # row preserved, not hard-deleted
        finally:
            db_session.close()

    def test_second_delete_on_soft_deleted_raffle_returns_404(
        self, client, free_org
    ):
        """After a soft-delete the resource is treated as non-existent.
        The delete endpoint uses get_owned_raffle (include_deleted=False),
        so re-calling DELETE on an already-deleted raffle correctly returns 404."""
        raffle_id = create_raffle(client, free_org["headers"])
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])
        resp = client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])
        assert resp.status_code == 404

    def test_deleted_raffle_returns_404_on_get(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])
        resp = client.get(f"/raffles/{raffle_id}", headers=free_org["headers"])
        assert resp.status_code == 404
