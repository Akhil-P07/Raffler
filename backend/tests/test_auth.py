"""Tests for POST /auth/login, POST /orgs, and POST /orgs/{id}/rotate-key."""
import pytest

from tests.conftest import create_org


class TestLogin:
    def test_valid_credentials_return_jwt(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "changeme"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    def test_wrong_password_returns_401(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_wrong_email_returns_401(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "notadmin@example.com", "password": "changeme"},
        )
        assert resp.status_code == 401

    def test_missing_body_returns_422(self, client):
        resp = client.post("/auth/login", json={})
        assert resp.status_code == 422

    def test_invalid_email_format_returns_422(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "not-an-email", "password": "changeme"},
        )
        assert resp.status_code == 422


class TestCreateOrg:
    def test_create_org_returns_api_key_once(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "My Org", "plan": "free"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "api_key" in body
        assert body["api_key"].startswith("rk_")
        assert body["plan"] == "free"
        assert body["name"] == "My Org"

    def test_api_key_embeds_org_id(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "Key Test Org", "plan": "free"},
            headers=admin_headers,
        )
        body = resp.json()
        org_id = body["id"]
        api_key = body["api_key"]
        # Format: rk_<org_id>.<secret>
        assert api_key.startswith(f"rk_{org_id}.")

    def test_create_org_requires_admin_jwt(self, client):
        resp = client.post("/orgs", json={"name": "Hacker Org", "plan": "free"})
        assert resp.status_code == 401

    def test_create_org_with_invalid_plan_returns_422(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "Bad Plan Org", "plan": "enterprise"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_org_with_club_plan(self, client, admin_headers):
        resp = client.post(
            "/orgs",
            json={"name": "Club Org", "plan": "club"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["plan"] == "club"


class TestKeyRotation:
    def test_rotate_key_returns_new_key(self, client, admin_headers):
        org_id, old_key = create_org(client, admin_headers, name="Rotate Org")
        resp = client.post(
            f"/orgs/{org_id}/rotate-key", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == org_id
        assert "api_key" in body
        assert body["api_key"] != old_key
        assert body["api_key"].startswith("rk_")

    def test_old_key_returns_401_after_rotation(self, client, admin_headers):
        org_id, old_key = create_org(client, admin_headers, name="Rotate Org 2")
        # Create a raffle with old key to verify access first.
        resp = client.post(
            "/raffles",
            json={"name": "Pre-rotation Raffle"},
            headers={"X-API-Key": old_key},
        )
        assert resp.status_code == 201

        # Rotate the key.
        client.post(f"/orgs/{org_id}/rotate-key", headers=admin_headers)

        # Old key must now fail.
        resp = client.post(
            "/raffles",
            json={"name": "Post-rotation Raffle"},
            headers={"X-API-Key": old_key},
        )
        assert resp.status_code == 401

    def test_new_key_works_after_rotation(self, client, admin_headers):
        org_id, _ = create_org(client, admin_headers, name="Rotate Org 3")
        resp = client.post(
            f"/orgs/{org_id}/rotate-key", headers=admin_headers
        )
        new_key = resp.json()["api_key"]
        resp = client.post(
            "/raffles",
            json={"name": "Post-rotation Raffle"},
            headers={"X-API-Key": new_key},
        )
        assert resp.status_code == 201

    def test_rotate_key_on_unknown_org_returns_404(self, client, admin_headers):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.post(
            f"/orgs/{fake_id}/rotate-key", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_rotate_key_requires_admin_jwt(self, client, admin_headers):
        org_id, _ = create_org(client, admin_headers, name="Rotate Org 4")
        resp = client.post(f"/orgs/{org_id}/rotate-key")
        assert resp.status_code == 401
