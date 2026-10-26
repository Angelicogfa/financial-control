"""Integration tests for single-user authentication (item 9.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from controllers.auth.dependencies import require_user
from core.security import SESSION_COOKIE, hash_password, main, verify_password
from core.settings import Settings, get_settings

PASSWORD = "correct horse battery"
SECRET = "s" * 64


@pytest.fixture
def secured(api: SimpleNamespace) -> TestClient:
    settings = Settings(
        _env_file=None,
        auth_username="owner",
        auth_password_hash=hash_password(PASSWORD),
        auth_jwt_secret=SECRET,
    )
    api.app.dependency_overrides.pop(require_user)
    api.app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(api.app)


def test_protected_routes_require_a_session(secured: TestClient) -> None:
    resp = secured.get("/api/v1/assets")

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHENTICATED"
    assert secured.get("/api/v1/health").status_code == 200
    assert secured.get("/api/v1/ready").status_code == 200


def test_login_sets_httponly_cookie_and_unlocks_api(secured: TestClient) -> None:
    resp = secured.post("/api/v1/auth/login", json={"username": "owner", "password": PASSWORD})

    assert resp.status_code == 200
    assert resp.json()["username"] == "owner"
    cookie = resp.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert secured.get("/api/v1/assets").status_code == 200
    assert secured.get("/api/v1/auth/me").json()["username"] == "owner"


def test_wrong_credentials_are_rejected(secured: TestClient) -> None:
    for username, password in (("owner", "nope"), ("intruder", PASSWORD)):
        resp = secured.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 401


def test_bearer_token_and_expired_token(secured: TestClient) -> None:
    def token(minutes: int) -> str:
        exp = datetime.now(UTC) + timedelta(minutes=minutes)
        return jwt.encode({"sub": "owner", "exp": exp}, SECRET, algorithm="HS256")

    ok = secured.get("/api/v1/assets", headers={"Authorization": f"Bearer {token(5)}"})
    expired = secured.get("/api/v1/assets", headers={"Authorization": f"Bearer {token(-5)}"})
    forged = secured.get(
        "/api/v1/assets",
        headers={"Authorization": "Bearer " + jwt.encode({"sub": "owner"}, "x" * 64, "HS256")},
    )

    assert ok.status_code == 200
    assert expired.json()["detail"] == "Session expired"
    assert forged.status_code == 401


def test_logout_clears_cookie(secured: TestClient) -> None:
    secured.post("/api/v1/auth/login", json={"username": "owner", "password": PASSWORD})

    resp = secured.post("/api/v1/auth/logout")

    assert resp.status_code == 204
    assert f'{SESSION_COOKIE}=""' in resp.headers["set-cookie"]


def test_unconfigured_auth_answers_503(api: SimpleNamespace) -> None:
    api.app.dependency_overrides.pop(require_user)
    api.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    client = TestClient(api.app)

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "x"})

    assert login.status_code == 503
    assert login.json()["code"] == "AUTH_NOT_CONFIGURED"
    assert client.get("/api/v1/assets").status_code == 503


def test_password_hashing_and_cli(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:
    hashed = hash_password(PASSWORD)
    assert verify_password(hashed, PASSWORD)
    assert not verify_password(hashed, "other")
    assert not verify_password("not-a-hash", PASSWORD)

    assert main(["new-secret"]) == 0
    assert capsys.readouterr().out.startswith("AUTH_JWT_SECRET=")

    monkeypatch.setattr("getpass.getpass", lambda _prompt: PASSWORD)
    assert main(["hash-password"]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("AUTH_PASSWORD_HASH='$argon2id$") and line.endswith("'")
    assert main([]) == 2
