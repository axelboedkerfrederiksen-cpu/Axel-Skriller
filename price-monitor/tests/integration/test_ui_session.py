from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.api.ui_auth import validate_ui_session
from price_monitor.config import Settings
from price_monitor.db.session import get_db_session
from price_monitor.main import create_app


def _protected_app(
    factory: sessionmaker[Session],
    tmp_path: Path,
) -> tuple[TestClient, str]:
    token = "a-secure-test-token-that-is-long-enough"
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        api_token=token,
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), token


def test_ui_session_authenticates_without_exposing_or_storing_the_access_key(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    http, token = _protected_app(session_factory, tmp_path)
    with http:
        status = http.get("/session")
        assert status.json() == {"authenticated": False, "protected": True}

        missing_marker = http.post("/session", json={"access_key": token})
        assert missing_marker.status_code == 403

        rejected = http.post(
            "/session",
            headers={"X-Price-Monitor-UI": "1"},
            json={"access_key": "wrong"},
        )
        assert rejected.status_code == 401
        assert token not in rejected.text

        oversized_secret = "s" * 5_000
        oversized = http.post(
            "/session",
            headers={"X-Price-Monitor-UI": "1"},
            json={"access_key": oversized_secret},
        )
        assert oversized.status_code == 400
        assert oversized_secret not in oversized.text

        logged_in = http.post(
            "/session",
            headers={"X-Price-Monitor-UI": "1"},
            json={"access_key": token},
        )
        assert logged_in.status_code == 200
        assert logged_in.json() == {"authenticated": True, "protected": True}
        cookie = logged_in.headers["set-cookie"]
        assert "pm_ui_session=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert token not in cookie
        assert http.get("/session").json()["authenticated"] is True
        assert http.get("/api/v1/customers").status_code == 200

        blocked_write = http.post(
            "/api/v1/customers",
            json={
                "name": "Blocked",
                "slug": "blocked",
                "webshop_url": "https://blocked.example.com",
            },
        )
        assert blocked_write.status_code == 403
        created = http.post(
            "/api/v1/customers",
            headers={"X-Price-Monitor-UI": "1"},
            json={
                "name": "Store",
                "slug": "store",
                "webshop_url": "https://store.example.com",
            },
        )
        assert created.status_code == 201

        logged_out = http.delete("/session", headers={"X-Price-Monitor-UI": "1"})
        assert logged_out.status_code == 200
        assert logged_out.json() == {"authenticated": False, "protected": True}
        assert http.get("/api/v1/customers").status_code == 401


def test_bearer_mutations_remain_compatible_and_do_not_need_the_ui_marker(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    http, token = _protected_app(session_factory, tmp_path)
    with http:
        response = http.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Bearer Store",
                "slug": "bearer-store",
                "webshop_url": "https://bearer.example.com",
            },
        )
    assert response.status_code == 201


def test_tampered_ui_session_cookie_is_rejected(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    http, _ = _protected_app(session_factory, tmp_path)
    with http:
        http.cookies.set("pm_ui_session", "v1.1.invalid.invalid")
        response = http.get("/api/v1/customers")
    assert response.status_code == 401


def test_unicode_tokens_are_rejected_and_malformed_unicode_cookie_is_safe() -> None:
    with pytest.raises(ValueError, match="ASCII"):
        Settings(api_token="å" * 32)

    settings = Settings(api_token="an-ascii-token-that-is-long-enough")
    assert not validate_ui_session("v1.1.å." + "x" * 43, settings)
