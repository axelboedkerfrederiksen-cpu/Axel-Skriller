from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.db.session import get_db_session
from price_monitor.main import create_app

pytestmark = pytest.mark.integration


@contextmanager
def _client(factory: sessionmaker[Session], tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        cron_secret="a-secure-cron-secret-that-is-long-enough",
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.state.session_factory = factory
    with TestClient(app) as client:
        yield client


def test_cron_endpoint_is_protected_and_handles_an_empty_queue(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _client(session_factory, tmp_path) as http:
        assert http.get("/api/cron/monitor").status_code == 401
        response = http.get(
            "/api/cron/monitor",
            headers={
                "Authorization": "Bearer a-secure-cron-secret-that-is-long-enough",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "queued": 0, "processed": 0}
