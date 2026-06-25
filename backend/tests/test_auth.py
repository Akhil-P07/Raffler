"""Tests for session auth: email/password signup + login, /me, the admin
premium allowlist, and plan evaluation. There are no API keys."""


def _register(client, email, password="password123", org_name="Acme"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "org_name": org_name},
    )


class TestSignup:
    def test_register_returns_session_and_free_plan(self, client):
        r = _register(client, "a@example.com")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["email"] == "a@example.com"
        assert body["org"]["plan"] == "free"
        assert body["org"]["name"] == "Acme"
        # No API key anywhere in the response.
        assert "api_key" not in body and "api_key" not in body["org"]

    def test_email_is_normalized_lowercase(self, client):
        r = _register(client, "MixedCase@Example.com")
        assert r.status_code == 201
        assert r.json()["email"] == "mixedcase@example.com"

    def test_duplicate_email_returns_409(self, client):
        _register(client, "dup@example.com")
        r = _register(client, "DUP@example.com")
        assert r.status_code == 409

    def test_short_password_returns_422(self, client):
        r = _register(client, "x@example.com", password="short")
        assert r.status_code == 422

    def test_default_org_name_from_email(self, client):
        r = client.post(
            "/auth/register",
            json={"email": "noorg@example.com", "password": "password123"},
        )
        assert r.json()["org"]["name"] == "noorg"


class TestLogin:
    def test_login_success(self, client):
        _register(client, "u@example.com", password="password123")
        r = client.post(
            "/auth/login", json={"email": "u@example.com", "password": "password123"}
        )
        assert r.status_code == 200
        assert r.json()["access_token"]

    def test_login_wrong_password_401(self, client):
        _register(client, "u@example.com", password="password123")
        r = client.post(
            "/auth/login", json={"email": "u@example.com", "password": "nope"}
        )
        assert r.status_code == 401

    def test_login_unknown_email_401(self, client):
        r = client.post(
            "/auth/login", json={"email": "ghost@example.com", "password": "whatever1"}
        )
        assert r.status_code == 401


class TestSession:
    def test_me_returns_account(self, client):
        token = _register(client, "me@example.com").json()["access_token"]
        r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "me@example.com"
        assert r.json()["org"]["plan"] == "free"

    def test_me_without_token_401(self, client):
        assert client.get("/me").status_code == 401

    def test_me_with_garbage_token_401(self, client):
        r = client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_org_scoped_requires_session(self, client):
        assert client.get("/raffles").status_code == 401

    def test_patch_org_updates_name_and_goc(self, client):
        token = _register(client, "og@example.com").json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        r = client.patch(
            "/org", json={"name": "New Name", "goc_id": "12-345"}, headers=h
        )
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"
        assert r.json()["goc_id"] == "12-345"
        # Clearing goc_id with null works.
        r = client.patch("/org", json={"goc_id": None}, headers=h)
        assert r.json()["goc_id"] is None


class TestPremiumAllowlist:
    def test_env_premium_email_gets_club(self, client):
        # club@test.example is in PREMIUM_EMAILS (conftest).
        r = _register(client, "club@test.example")
        assert r.json()["org"]["plan"] == "club"

    def test_admin_login(self, client):
        r = client.post(
            "/auth/admin/login",
            json={"email": "admin@example.com", "password": "changeme"},
        )
        assert r.status_code == 200
        assert r.json()["access_token"]

    def test_admin_login_bad_password_401(self, client):
        r = client.post(
            "/auth/admin/login",
            json={"email": "admin@example.com", "password": "wrong"},
        )
        assert r.status_code == 401

    def test_admin_can_add_and_list_premium(self, client, admin_headers):
        r = client.post(
            "/admin/premium",
            json={"email": "vip@example.com"},
            headers=admin_headers,
        )
        assert r.status_code == 201
        emails = [
            e["email"]
            for e in client.get("/admin/premium", headers=admin_headers).json()
        ]
        assert "vip@example.com" in emails

    def test_premium_endpoints_require_admin(self, client):
        token = _register(client, "norm@example.com").json()["access_token"]
        # A normal user session is not an admin token.
        r = client.get(
            "/admin/premium", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 401
        assert client.get("/admin/premium").status_code == 401

    def test_adding_email_promotes_existing_user_on_next_login(
        self, client, admin_headers
    ):
        _register(client, "promote@example.com", password="password123")
        client.post(
            "/admin/premium",
            json={"email": "promote@example.com"},
            headers=admin_headers,
        )
        r = client.post(
            "/auth/login",
            json={"email": "promote@example.com", "password": "password123"},
        )
        assert r.json()["org"]["plan"] == "club"

    def test_removing_email_demotes_on_next_login(self, client, admin_headers):
        client.post(
            "/admin/premium",
            json={"email": "demote@example.com"},
            headers=admin_headers,
        )
        _register(client, "demote@example.com", password="password123")  # club now
        client.delete("/admin/premium/demote@example.com", headers=admin_headers)
        r = client.post(
            "/auth/login",
            json={"email": "demote@example.com", "password": "password123"},
        )
        assert r.json()["org"]["plan"] == "free"


class TestGoogle:
    def test_google_login_503_when_unconfigured(self, client):
        # GOOGLE_CLIENT_ID/SECRET are unset in the test env.
        assert client.get("/auth/google/login").status_code == 503
