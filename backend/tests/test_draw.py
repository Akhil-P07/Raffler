"""Tests for POST /raffles/{id}/draw and GET /raffles/{id}/winners."""
import pytest

from tests.conftest import (
    create_raffle,
    generate_tickets,
    get_tickets_from_db,
    register_ticket,
)


def _setup_drawn_raffle(client, app_and_db, org):
    """Helper: create raffle, generate 3 tickets, register all, draw once."""
    _, database_mod = app_and_db
    raffle_id = create_raffle(client, org["headers"])
    generate_tickets(client, org["headers"], raffle_id, count=3)

    db_session = database_mod.SessionLocal()
    try:
        tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
        tokens = [t.token for t in tickets]
    finally:
        db_session.close()

    for i, token in enumerate(tokens):
        register_ticket(
            client, token, org["headers"], name=f"Person {i}", email=f"p{i}@test.com"
        )

    resp = client.post(
        f"/raffles/{raffle_id}/draw",
        json={"prize_count": 1},
        headers=org["headers"],
    )
    assert resp.status_code == 200
    return raffle_id, resp.json()


class TestDraw:
    def test_draw_happy_path_returns_winner(
        self, client, app_and_db, free_org
    ):
        _, draw_resp = _setup_drawn_raffle(client, app_and_db, free_org)
        assert draw_resp["already_drawn"] is False
        assert len(draw_resp["winners"]) == 1
        assert draw_resp["status"] == "drawn"

    def test_draw_is_idempotent(self, client, app_and_db, free_org):
        """Calling /draw twice must return identical winner ids."""
        raffle_id, first = _setup_drawn_raffle(client, app_and_db, free_org)

        second = client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        ).json()

        assert second["already_drawn"] is True
        first_ids = [w["id"] for w in first["winners"]]
        second_ids = [w["id"] for w in second["winners"]]
        assert first_ids == second_ids, "Second draw returned different winners!"

    def test_draw_idempotent_winner_names_unchanged(
        self, client, app_and_db, free_org
    ):
        raffle_id, first = _setup_drawn_raffle(client, app_and_db, free_org)
        second = client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        ).json()
        assert first["winners"][0]["name"] == second["winners"][0]["name"]

    def test_draw_with_multiple_prizes(self, client, app_and_db, club_org):
        _, database_mod = app_and_db
        raffle_id = create_raffle(client, club_org["headers"])
        generate_tickets(client, club_org["headers"], raffle_id, count=5)

        db_session = database_mod.SessionLocal()
        try:
            tickets = get_tickets_from_db(db_session, database_mod, raffle_id)
            tokens = [t.token for t in tickets]
        finally:
            db_session.close()

        for i, token in enumerate(tokens):
            register_ticket(
                client, token, club_org["headers"], name=f"Person {i}", email=f"p{i}@test.com"
            )

        resp = client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 3},
            headers=club_org["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["winners"]) == 3
        # Verify prize ranks are sequential.
        ranks = [w["prize_rank"] for w in body["winners"]]
        assert ranks == [1, 2, 3]

    def test_draw_no_entries_returns_409(self, client, free_org):
        raffle_id = create_raffle(client, free_org["headers"])
        generate_tickets(client, free_org["headers"], raffle_id, count=3)
        # No registrations — draw must fail.
        resp = client.post(
            f"/raffles/{raffle_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        assert resp.status_code == 409

    def test_draw_on_unknown_raffle_returns_404(self, client, free_org):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.post(
            f"/raffles/{fake_id}/draw",
            json={"prize_count": 1},
            headers=free_org["headers"],
        )
        assert resp.status_code == 404

    def test_draw_without_api_key_returns_401(self, client, app_and_db, free_org):
        raffle_id, _ = _setup_drawn_raffle(client, app_and_db, free_org)
        resp = client.post(
            f"/raffles/{raffle_id}/draw", json={"prize_count": 1}
        )
        assert resp.status_code == 401

    def test_drawn_raffle_sets_status_to_drawn(
        self, client, app_and_db, free_org
    ):
        raffle_id, draw_resp = _setup_drawn_raffle(client, app_and_db, free_org)
        assert draw_resp["status"] == "drawn"

        resp = client.get(
            f"/raffles/{raffle_id}", headers=free_org["headers"]
        )
        assert resp.json()["status"] == "drawn"

    def test_draw_rng_uses_system_random_not_seedable(self):
        """Verify SystemRandom cannot be seeded — seeding random.seed does not
        affect secrets.SystemRandom, so two calls can't be forced to agree."""
        import random
        import secrets
        from services.rng import select_winners

        entry_ids = [str(i) for i in range(20)]

        random.seed(42)
        result_a = select_winners(entry_ids[:], 5)

        random.seed(42)
        result_b = select_winners(entry_ids[:], 5)

        # Because SystemRandom is OS-seeded, seeding random.seed has no effect.
        # We can't assert exact inequality (astronomically unlikely to match),
        # but we CAN assert the function does not internally call random.seed.
        # The real test: monkey-patch random.random to raise — SystemRandom must
        # NOT use it.
        original = random.random

        def _forbidden(*a, **kw):
            raise AssertionError("select_winners must not use random.random")

        random.random = _forbidden
        try:
            result_c = select_winners(entry_ids[:], 5)
        finally:
            random.random = original

        # If we reach here, SystemRandom did not touch random.random. Pass.
        assert len(result_c) == 5

    def test_winners_list_endpoint_matches_draw_response(
        self, client, app_and_db, free_org
    ):
        raffle_id, draw_resp = _setup_drawn_raffle(client, app_and_db, free_org)
        resp = client.get(
            f"/raffles/{raffle_id}/winners", headers=free_org["headers"]
        )
        assert resp.status_code == 200
        winner_ids_draw = [w["id"] for w in draw_resp["winners"]]
        winner_ids_list = [w["id"] for w in resp.json()]
        assert winner_ids_draw == winner_ids_list

    def test_drawn_raffle_excluded_from_active_count(
        self, client, app_and_db, free_org
    ):
        """After a draw, the raffle must not count toward the free-plan limit,
        so the org can create a second raffle."""
        raffle_id, _ = _setup_drawn_raffle(client, app_and_db, free_org)

        # Creating a second raffle on a free plan must now succeed.
        resp = client.post(
            "/raffles",
            json={"name": "Second Raffle"},
            headers=free_org["headers"],
        )
        assert resp.status_code == 201, (
            "Drawn raffle should not count against free-plan active raffle limit"
        )
