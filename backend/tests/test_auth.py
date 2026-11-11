from datetime import timedelta

import pytest
from app.config import Settings, settings
from app.models import Session as LoginSession
from app.models import User, utcnow
from conftest import PASSWORD, login
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_public_health_and_controlled_operations(client):
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    for path in ("/health/ready", "/sites", "/auth/me", "/openapi.json"):
        assert client.get("/api/v1" + path).status_code == 401
    login(client)
    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}
    assert client.get("/api/v1/openapi.json").status_code == 200


def test_session_cookie_csrf_logout(client, database):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").json()["user"]["username"] == "admin"
    assert client.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Origin": "https://evil.example", "X-CSRF-Token": token}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://testserver", "X-CSRF-Token": token}
        ).status_code
        == 204
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(database) as db:
        assert db.scalar(select(LoginSession)) is None


def test_bad_login_and_rate_limit(client):
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "unknown", "password": "wrong"},
            headers={"Origin": "http://testserver"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "unknown", "password": "wrong"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 429 and response.headers["retry-after"] == "900"
    assert (
        client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 403
    )


@pytest.mark.parametrize(
    "username,expected", [("admin", ["ONE", "TWO"]), ("auditor", ["ONE"]), ("manager", ["TWO"])]
)
def test_live_site_permissions(client, database, username, expected):
    login(client, username)
    assert [item["code"] for item in client.get("/api/v1/sites").json()] == expected
    with Session(database) as db:
        db.get(User, {"admin": 1, "auditor": 2, "manager": 3}[username]).active = False
        db.commit()
    assert client.get("/api/v1/sites").status_code == 401


def test_password_change_revokes_all_sessions(client):
    login(client)
    # A second login replaces the browser's old session, while other device sessions remain revocable.
    token = login(client)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a-new-long-password"},
        headers={"Origin": "http://testserver", "X-CSRF-Token": token},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_denied(client, database):
    login(client)
    with Session(database) as db:
        db.scalar(select(LoginSession)).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_secure_cookie(client, monkeypatch):
    monkeypatch.setenv("SECURE_COOKIES", "true")
    settings.cache_clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert "Secure" in response.headers["set-cookie"]


def test_production_refuses_insecure_configuration():
    with pytest.raises(ValueError):
        Settings(environment="production", secure_cookies=False)
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            secure_cookies=True,
            app_origin="https://audit.example",
            trusted_hosts="*",
        )


def test_validation_does_not_echo_password(client):
    response = client.post("/api/v1/auth/login", json={"username": "X", "password": "do-not-echo-me"})
    assert response.status_code == 422
    assert "do-not-echo-me" not in response.text
