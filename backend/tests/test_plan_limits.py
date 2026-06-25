"""Tests for plan-limit enforcement (free vs club)."""
import pytest

from tests.conftest import create_raffle, generate_tickets, get_tickets_from_db, register_ticket


class TestFreeRaffleLimit:
    """Free tier: at most 5 raffles over the org's LIFETIME. Deleted and drawn
    raffles still count, so they never free a slot."""

    def test_free_org_can_create_up_to_5(self, client, free_org):
        for i in range(5):
            resp = client.post(
                "/raffles", json={"name": f"R{i}"}, headers=free_org["headers"]
            )
            assert resp.status_code == 201, resp.text
        # The 6th is blocked.
        resp = client.post(
            "/raffles", json={"name": "R6"}, headers=free_org["headers"]
        )
        assert resp.status_code == 403

    def test_deleted_raffles_still_count_toward_lifetime(self, client, free_org):
        ids = [
            client.post(
                "/raffles", json={"name": f"R{i}"}, headers=free_org["headers"]
            ).json()["id"]
            for i in range(5)
        ]
        # Delete two — they still count, so a 6th is still blocked.
        client.delete(f"/raffles/{ids[0]}", headers=free_org["headers"])
        client.delete(f"/raffles/{ids[1]}", headers=free_org["headers"])
        resp = client.post(
            "/raffles", json={"name": "R6"}, headers=free_org["headers"]
        )
        assert resp.status_code == 403

    def test_drawn_raffle_still_counts_toward_lifetime(
        self, client, app_and_db, free_org
    ):
        _, database_mod = app_and_db
        ids = [
            client.post(
                "/raffles", json={"name": f"R{i}"}, headers=free_org["headers"]
            ).json()["id"]
            for i in range(5)
        ]
        generate_tickets(client, free_org["headers"], ids[0], count=1)
        s = database_mod.SessionLocal()
        try:
            token = get_tickets_from_db(s, database_mod, ids[0])[0].token
        finally:
            s.close()
        register_ticket(client, token, free_org["headers"])
        client.post(
            f"/raffles/{ids[0]}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        # The drawn raffle still counts — 6th blocked.
        resp = client.post(
            "/raffles", json={"name": "R6"}, headers=free_org["headers"]
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
    def test_club_org_can_create_many_raffles(self, client, club_org):
        # Well past the free lifetime cap of 5.
        for i in range(7):
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
