"""Tests for plan-limit enforcement (free vs club)."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db, register_ticket


class TestFreeRaffleLimit:
    def test_free_org_can_create_one_raffle(self, client, free_org):
        resp = client.post(
            "/raffles", json={"name": "First"}, headers=free_org["headers"]
        )
        assert resp.status_code == 201

    def test_free_org_blocked_on_second_active_raffle(self, client, free_org):
        """Free plan allows only 1 active raffle at a time."""
        client.post(
            "/raffles", json={"name": "First"}, headers=free_org["headers"]
        )
        resp = client.post(
            "/raffles", json={"name": "Second"}, headers=free_org["headers"]
        )
        assert resp.status_code == 403

    def test_free_org_can_create_second_raffle_after_draw(
        self, client, app_and_db, free_org
    ):
        """A drawn raffle no longer counts as active — free org gets a new slot."""
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=1)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            token = tickets[0].token
        finally:
            db_session.close()

        register_ticket(client, token, free_org["headers"])
        client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )

        # Now the first raffle is drawn — should be able to create another.
        resp = client.post(
            "/raffles", json={"name": "Second"}, headers=free_org["headers"]
        )
        assert resp.status_code == 201

    def test_free_org_can_create_second_raffle_after_soft_delete(
        self, client, free_org
    ):
        """A soft-deleted raffle no longer counts as active either."""
        raffle_id = create_raffle(client, free_org["headers"])
        client.delete(f"/raffles/{raffle_id}", headers=free_org["headers"])

        resp = client.post(
            "/raffles", json={"name": "Second"}, headers=free_org["headers"]
        )
        assert resp.status_code == 201

    def test_free_org_blocked_on_second_raffle_after_closing_first(
        self, client, free_org
    ):
        """Closed (not drawn) still counts as active."""
        raffle_id = create_raffle(client, free_org["headers"])
        client.patch(
            f"/raffles/{raffle_id}",
            json={"status": "closed"},
            headers=free_org["headers"],
        )
        resp = client.post(
            "/raffles", json={"name": "Second"}, headers=free_org["headers"]
        )
        assert resp.status_code == 403


class TestFreeTicketLimit:
    def test_free_org_can_generate_50_tickets(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 50},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["created"] == 50

    def test_free_org_blocked_at_51st_ticket(self, client, free_org):
        """Exactly 51 tickets must fail on a free plan."""
        raffle_id = create_raffle(client, free_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 51},
            headers=free_org["headers"],
        )
        assert resp.status_code == 403

    def test_free_org_blocked_adding_tickets_beyond_50(self, client, free_org):
        """50 + 1 must also fail."""
        raffle_id = create_raffle(client, free_org["headers"])
        client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 50},
            headers=free_org["headers"],
        )
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 1},
            headers=free_org["headers"],
        )
        assert resp.status_code == 403

    def test_free_org_can_add_tickets_if_still_under_50(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 25},
            headers=free_org["headers"],
        )
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 25},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201


class TestClubPlanUnlimited:
    def test_club_org_can_create_multiple_raffles(self, client, club_org):
        for i in range(3):
            resp = client.post(
                "/raffles",
                json={"name": f"Raffle {i}"},
                headers=club_org["headers"],
            )
            assert resp.status_code == 201

    def test_club_org_can_generate_over_50_tickets(self, client, club_org):
        raffle_id = create_raffle(client, club_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 100},
            headers=club_org["headers"],
        )
        assert resp.status_code == 201
        assert resp.json()["created"] == 100

    def test_club_org_can_generate_200_tickets(self, client, club_org):
        raffle_id = create_raffle(client, club_org["headers"])
        resp = client.post(
            f"/raffles/{raffle_id}/tickets",
            json={"count": 200},
            headers=club_org["headers"],
        )
        assert resp.status_code == 201
