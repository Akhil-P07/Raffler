"""Multi-org membership: roles, invites, org switching, and the owner-only
restrictions that protect against a rogue invited member."""

from tests.conftest import (
    create_raffle,
    generate_tickets,
    get_tickets_from_db,
    invite_and_accept,
    register_ticket,
)


def _owner_raffle_with_tickets(client, app_and_db, owner, count=3):
    raffle_id = create_raffle(client, owner["headers"])
    generate_tickets(client, owner["headers"], raffle_id, count=count)
    _, database_mod = app_and_db
    s = database_mod.SessionLocal()
    try:
        tokens = [t.token for t in get_tickets_from_db(s, database_mod, raffle_id)]
        tids = [t.id for t in get_tickets_from_db(s, database_mod, raffle_id)]
    finally:
        s.close()
    return raffle_id, tokens, tids


class TestRolesAndSignup:
    def test_signup_is_owner_with_one_org(self, client, free_org):
        # free_org fixture already asserts 201; re-check the auth shape.
        r = client.post(
            "/auth/register",
            json={"email": "x@test.example", "password": "password123"},
        ).json()
        assert r["role"] == "owner"
        assert len(r["orgs"]) == 1 and r["orgs"][0]["role"] == "owner"
        assert "api_key" not in r

    def test_me_includes_role_and_orgs(self, client, free_org):
        me = client.get("/me", headers=free_org["headers"]).json()
        assert me["role"] == "owner"
        assert len(me["orgs"]) == 1


class TestInviteAccept:
    def test_invite_lists_as_pending(self, client, free_org):
        client.post("/org/members", json={"email": "m@test.example"}, headers=free_org["headers"])
        members = client.get("/org/members", headers=free_org["headers"]).json()
        assert any(m["email"] == "m@test.example" and m["status"] == "invited" for m in members)

    def test_new_account_accept_needs_password(self, client, app_and_db, free_org):
        member = invite_and_accept(client, app_and_db, free_org["headers"], "newmem@test.example")
        assert member["role"] == "member"

    def test_accept_without_password_for_new_account_422(self, client, app_and_db, free_org):
        _, database_mod = app_and_db
        client.post("/org/members", json={"email": "np@test.example"}, headers=free_org["headers"])
        s = database_mod.SessionLocal()
        try:
            token = s.query(database_mod.OrgInvite).filter(
                database_mod.OrgInvite.email == "np@test.example"
            ).first().token
        finally:
            s.close()
        assert client.get(f"/invites/{token}").json()["needs_password"] is True
        assert client.post(f"/invites/{token}/accept", json={}).status_code == 422

    def test_existing_account_attaches_without_password(self, client, app_and_db, free_org, org_b):
        # org_b's owner gets invited to free_org; existing account -> no password.
        _, database_mod = app_and_db
        client.post("/org/members", json={"email": "orgb@test.example"}, headers=free_org["headers"])
        s = database_mod.SessionLocal()
        try:
            token = s.query(database_mod.OrgInvite).filter(
                database_mod.OrgInvite.email == "orgb@test.example"
            ).first().token
        finally:
            s.close()
        assert client.get(f"/invites/{token}").json()["needs_password"] is False
        r = client.post(f"/invites/{token}/accept", json={})
        assert r.status_code == 200 and r.json()["role"] == "member"
        assert len(r.json()["orgs"]) == 2  # now in both orgs

    def test_already_member_invite_409(self, client, app_and_db, free_org):
        invite_and_accept(client, app_and_db, free_org["headers"], "dup@test.example")
        r = client.post("/org/members", json={"email": "dup@test.example"}, headers=free_org["headers"])
        assert r.status_code == 409

    def test_unknown_invite_token_404(self, client):
        assert client.get("/invites/nope").status_code == 404
        assert client.post("/invites/nope/accept", json={"password": "password123"}).status_code == 404


class TestMemberRestrictions:
    def test_member_cannot_manage(self, client, app_and_db, free_org, member_of_free):
        mh = member_of_free["headers"]
        raffle_id, tokens, tids = _owner_raffle_with_tickets(client, app_and_db, free_org)
        # owner-only actions -> 403 for a member
        assert client.post(f"/raffles/{raffle_id}/tickets", json={"count": 1}, headers=mh).status_code == 403
        assert client.get(f"/raffles/{raffle_id}/tickets/sheet", headers=mh).status_code == 403
        assert client.get(f"/tickets/{tids[0]}/preview", headers=mh).status_code == 403
        assert client.get(f"/tickets/{tids[0]}/qr", headers=mh).status_code == 403
        assert client.post("/raffles", json={"name": "X"}, headers=mh).status_code == 403
        assert client.delete(f"/raffles/{raffle_id}", headers=mh).status_code == 403
        assert client.post(f"/raffles/{raffle_id}/draw", json={"prize_count": 1}, headers=mh).status_code == 403
        assert client.get("/org/members", headers=mh).status_code == 403
        assert client.patch("/org", json={"name": "Nope"}, headers=mh).status_code == 403

    def test_member_can_view_and_register(self, client, app_and_db, free_org, member_of_free):
        mh = member_of_free["headers"]
        raffle_id, tokens, _ = _owner_raffle_with_tickets(client, app_and_db, free_org)
        assert client.get("/raffles", headers=mh).status_code == 200
        assert client.get(f"/raffles/{raffle_id}", headers=mh).status_code == 200
        # member registers a scanned ticket (their job)
        assert register_ticket(client, tokens[0], mh).status_code == 201
        assert len(client.get(f"/raffles/{raffle_id}/entries", headers=mh).json()) == 1


class TestDeregister:
    def test_owner_deregister_frees_ticket(self, client, app_and_db, free_org, member_of_free):
        mh = member_of_free["headers"]
        oh = free_org["headers"]
        raffle_id, tokens, _ = _owner_raffle_with_tickets(client, app_and_db, free_org)
        register_ticket(client, tokens[0], mh)
        eid = client.get(f"/raffles/{raffle_id}/entries", headers=oh).json()[0]["id"]
        # member cannot deregister
        assert client.post(f"/raffles/{raffle_id}/entries/deregister", json={"entry_ids": [eid]}, headers=mh).status_code == 403
        # owner can
        r = client.post(f"/raffles/{raffle_id}/entries/deregister", json={"entry_ids": [eid]}, headers=oh)
        assert r.status_code == 200 and r.json()["deregistered"] == 1
        assert len(client.get(f"/raffles/{raffle_id}/entries", headers=oh).json()) == 0
        # ticket is registerable again
        assert register_ticket(client, tokens[0], mh).status_code == 201

    def test_deregister_blocked_after_draw(self, client, app_and_db, free_org, member_of_free):
        oh = free_org["headers"]
        raffle_id, tokens, _ = _owner_raffle_with_tickets(client, app_and_db, free_org)
        register_ticket(client, tokens[0], member_of_free["headers"])
        eid = client.get(f"/raffles/{raffle_id}/entries", headers=oh).json()[0]["id"]
        client.post(f"/raffles/{raffle_id}/draw", json={"prize_count": 1}, headers=oh)
        assert client.post(f"/raffles/{raffle_id}/entries/deregister", json={"entry_ids": [eid]}, headers=oh).status_code == 409


class TestSwitchAndRemove:
    def test_select_org_requires_membership(self, client, free_org):
        assert client.post(
            "/auth/select-org",
            json={"org_id": "00000000-0000-0000-0000-000000000000"},
            headers=free_org["headers"],
        ).status_code == 404

    def test_removed_member_token_stops_working(self, client, app_and_db, free_org, member_of_free):
        mh = member_of_free["headers"]
        assert client.get("/raffles", headers=mh).status_code == 200
        client.delete(
            f"/org/members/{member_of_free['email']}", headers=free_org["headers"]
        )
        # The membership is gone, so the old session no longer resolves an org.
        assert client.get("/raffles", headers=mh).status_code == 401

    def test_cannot_remove_only_owner(self, client, free_org):
        assert client.delete(
            f"/org/members/{free_org['email']}", headers=free_org["headers"]
        ).status_code == 400
