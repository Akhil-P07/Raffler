"""Forgot-password / reset-password flow.

Email delivery is config-gated off in tests, so we mint the reset token the
same way the endpoint does (from security helpers) to drive the reset.
"""
from .conftest import signup


def _reset_token_for(database_mod, email: str) -> str:
    """Build a valid reset token for `email`, mirroring the endpoint's logic."""
    import hashlib

    import security

    s = database_mod.SessionLocal()
    try:
        user = (
            s.query(database_mod.User)
            .filter(database_mod.User.email == email.lower())
            .first()
        )
        fp = hashlib.sha256(
            (user.password_hash or f"nopw:{user.id}").encode()
        ).hexdigest()[:16]
        token, _ = security.create_password_reset_token(user.id, fp)
        return token
    finally:
        s.close()


def test_forgot_password_is_generic_for_any_email(client):
    # Unknown email: still 200 with the same message (no account enumeration).
    resp = client.post("/auth/forgot-password", json={"email": "nobody@x.example"})
    assert resp.status_code == 200, resp.text
    assert "reset link" in resp.json()["message"].lower()


def test_reset_password_changes_login_and_is_single_use(client, app_and_db):
    _, database_mod = app_and_db
    signup(client, "reset@test.example", password="origpassword1")

    token = _reset_token_for(database_mod, "reset@test.example")

    # Old password works before reset.
    assert (
        client.post(
            "/auth/login",
            json={"email": "reset@test.example", "password": "origpassword1"},
        ).status_code
        == 200
    )

    # Reset to a new password.
    resp = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "brandnewpass1"},
    )
    assert resp.status_code == 200, resp.text

    # New password works; old one no longer does.
    assert (
        client.post(
            "/auth/login",
            json={"email": "reset@test.example", "password": "brandnewpass1"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login",
            json={"email": "reset@test.example", "password": "origpassword1"},
        ).status_code
        == 401
    )

    # The same token can't be reused — the fingerprint no longer matches.
    resp = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "yetanotherpw1"},
    )
    assert resp.status_code == 400, resp.text


def test_reset_password_rejects_garbage_token(client):
    resp = client.post(
        "/auth/reset-password",
        json={"token": "not-a-real-token", "password": "whateverpass1"},
    )
    assert resp.status_code == 400, resp.text
