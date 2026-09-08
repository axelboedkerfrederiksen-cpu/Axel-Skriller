from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.db.models import CompetitorProduct, ScrapeResult, ScraperHealth
from price_monitor.db.session import get_db_session
from price_monitor.domain.enums import FailureKind, HealthStatus, ResultStatus
from price_monitor.main import create_app

pytestmark = pytest.mark.integration


@contextmanager
def _client(factory: sessionmaker[Session], tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as client:
        yield client


def _create_queued_target(http: TestClient) -> tuple[UUID, UUID, UUID]:
    customer = http.post(
        "/api/v1/customers",
        json={
            "name": "Safe status shop",
            "slug": "safe-status-shop",
            "webshop_url": "https://shop.example.com",
        },
    ).json()
    competitor = http.post(
        f"/api/v1/customers/{customer['id']}/competitors",
        json={
            "name": "Books to Scrape",
            "base_url": "https://books.toscrape.com",
            "adapter_key": "books_to_scrape",
        },
    ).json()
    product = http.post(
        f"/api/v1/customers/{customer['id']}/products",
        json={"name": "A Light in the Attic"},
    ).json()
    target = http.post(
        f"/api/v1/products/{product['id']}/competitor-products",
        json={
            "competitor_id": competitor["id"],
            "product_url": (
                "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
            ),
        },
    ).json()
    queued = http.post(f"/api/v1/competitor-products/{target['id']}/scrapes").json()
    return UUID(target["id"]), UUID(competitor["id"]), UUID(queued["scrape_result_id"])


def test_monitoring_status_exposes_only_safe_operational_fields(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    attempted_at = datetime(2026, 9, 8, 8, 10, tzinfo=UTC)
    succeeded_at = datetime(2026, 9, 8, 7, 55, tzinfo=UTC)
    observed_at = datetime(2026, 9, 8, 7, 54, tzinfo=UTC)
    started_at = datetime(2026, 9, 8, 8, 9, tzinfo=UTC)
    finished_at = datetime(2026, 9, 8, 8, 10, tzinfo=UTC)

    with _client(session_factory, tmp_path) as http:
        target_id, _, result_id = _create_queued_target(http)
        with session_factory() as session:
            target = session.get(CompetitorProduct, target_id)
            result = session.get(ScrapeResult, result_id)
            assert target is not None
            assert result is not None
            target.last_attempt_at = attempted_at
            target.last_success_at = succeeded_at
            target.current_observed_at = observed_at
            target.consecutive_failures = 2
            result.status = ResultStatus.FAILED
            result.started_at = started_at
            result.finished_at = finished_at
            result.failure_kind = FailureKind.INTERNAL
            result.failure_code = "credentials_leaked_if_rendered"
            result.failure_message = "secret diagnostic text"
            result.validation_errors = [{"secret": "do not expose"}]
            result.extraction_evidence = {"token": "do not expose"}
            result.html_artifact_uri = "file:///private/artifact.html"
            result.html_sha256 = "a" * 64
            result.screenshot_uri = "file:///private/screenshot.png"
            session.commit()

        response = http.get(f"/api/v1/competitor-products/{target_id}/monitoring-status")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "target_id",
        "latest_job_status",
        "latest_job_queued_at",
        "latest_job_started_at",
        "latest_job_finished_at",
        "last_attempt_at",
        "last_success_at",
        "current_observed_at",
        "consecutive_failures",
    }
    assert body["target_id"] == str(target_id)
    assert body["latest_job_status"] == "failed"
    assert body["latest_job_started_at"] == "2026-09-08T08:09:00Z"
    assert body["latest_job_finished_at"] == "2026-09-08T08:10:00Z"
    assert body["last_attempt_at"] == "2026-09-08T08:10:00Z"
    assert body["last_success_at"] == "2026-09-08T07:55:00Z"
    assert body["current_observed_at"] == "2026-09-08T07:54:00Z"
    assert body["consecutive_failures"] == 2
    assert "secret" not in response.text
    assert "artifact" not in response.text
    assert "failure" not in set(body)


def test_health_summary_excludes_diagnostics_and_result_identifiers(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    attempted_at = datetime(2026, 9, 8, 8, 10, tzinfo=UTC)
    succeeded_at = datetime(2026, 9, 8, 7, 55, tzinfo=UTC)
    failed_at = datetime(2026, 9, 8, 8, 10, tzinfo=UTC)

    with _client(session_factory, tmp_path) as http:
        _, competitor_id, result_id = _create_queued_target(http)
        with session_factory() as session:
            health = session.get(ScraperHealth, competitor_id)
            assert health is not None
            health.status = HealthStatus.DEGRADED
            health.consecutive_repairable_failures = 3
            health.recent_failure_count = 4
            health.last_attempt_at = attempted_at
            health.last_success_at = succeeded_at
            health.last_failure_at = failed_at
            health.last_failure_kind = FailureKind.EXTRACTION
            health.last_failure_message = "private selector diagnostics"
            health.last_scrape_result_id = result_id
            session.commit()

        response = http.get(f"/api/v1/competitors/{competitor_id}/health-summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "competitor_id",
        "status",
        "consecutive_repairable_failures",
        "recent_failure_count",
        "last_attempt_at",
        "last_success_at",
        "last_failure_at",
        "last_failure_kind",
        "updated_at",
    }
    assert body["competitor_id"] == str(competitor_id)
    assert body["status"] == "degraded"
    assert body["consecutive_repairable_failures"] == 3
    assert body["recent_failure_count"] == 4
    assert body["last_failure_kind"] == "extraction"
    assert body["last_attempt_at"] == "2026-09-08T08:10:00Z"
    assert body["last_success_at"] == "2026-09-08T07:55:00Z"
    assert body["last_failure_at"] == "2026-09-08T08:10:00Z"
    assert "private selector diagnostics" not in response.text
    assert "last_failure_message" not in body
    assert "last_scrape_result_id" not in body


def test_safe_status_endpoints_return_not_found_for_unknown_resources(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    missing = "00000000-0000-0000-0000-000000000001"
    with _client(session_factory, tmp_path) as http:
        monitoring = http.get(f"/api/v1/competitor-products/{missing}/monitoring-status")
        health = http.get(f"/api/v1/competitors/{missing}/health-summary")

    assert monitoring.status_code == 404
    assert health.status_code == 404
