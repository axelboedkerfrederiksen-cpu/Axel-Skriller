from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.db.models import CompetitorProduct, PriceHistory, ScrapeResult, ScraperHealth
from price_monitor.db.session import get_db_session
from price_monitor.domain.enums import (
    Availability,
    ChangeKind,
    FetchMode,
    HealthStatus,
    ResultStatus,
)
from price_monitor.domain.types import utc_now
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


def _create_catalog(http: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    customer = http.post(
        "/api/v1/customers",
        json={
            "name": "Danish Webshop",
            "slug": "danish-webshop",
            "webshop_url": "https://shop.example.com",
            "default_currency": "DKK",
            "timezone": "Europe/Copenhagen",
        },
    ).json()
    competitor = http.post(
        f"/api/v1/customers/{customer['id']}/competitors",
        json={
            "name": "Books to Scrape",
            "base_url": "https://books.toscrape.com",
            "adapter_key": "books_to_scrape",
            "expected_currency": "DKK",
        },
    ).json()
    product = http.post(
        f"/api/v1/customers/{customer['id']}/products",
        json={
            "name": "Test Product",
            "sku": "SKU-1",
            "current_own_price": "100.00",
            "currency": "DKK",
        },
    ).json()
    target = http.post(
        f"/api/v1/products/{product['id']}/competitor-products",
        json={
            "competitor_id": competitor["id"],
            "product_url": "https://books.toscrape.com/catalogue/test-product/index.html",
            "expected_currency": "DKK",
        },
    ).json()
    return customer, target


def _record_prices(
    factory: sessionmaker[Session],
    target_id: str,
    *,
    now_offset: timedelta = timedelta(),
) -> None:
    now = utc_now() + now_offset
    with factory() as session:
        target = session.get(CompetitorProduct, UUID(target_id))
        assert target is not None
        observations = (
            ("dashboard-first", now - timedelta(hours=2), Decimal("90.00"), None),
            (
                "dashboard-second",
                now - timedelta(minutes=20),
                Decimal("80.00"),
                Decimal("90.00"),
            ),
        )
        for run_key, observed_at, price, previous_price in observations:
            result = ScrapeResult(
                run_key=run_key,
                competitor_product_id=target.id,
                status=ResultStatus.SUCCEEDED,
                observed_at=observed_at,
                finished_at=observed_at,
                scraper_revision="1",
                fetch_mode=FetchMode.HTTP,
                price=price,
                currency="DKK",
                availability=Availability.IN_STOCK,
                previous_price=previous_price,
                previous_currency="DKK" if previous_price is not None else None,
                is_price_change=previous_price is not None,
            )
            session.add(result)
            session.flush()
            change_amount = price - previous_price if previous_price is not None else None
            session.add(
                PriceHistory(
                    competitor_product_id=target.id,
                    scrape_result_id=result.id,
                    observed_at=observed_at,
                    price=price,
                    currency="DKK",
                    availability=Availability.IN_STOCK,
                    previous_price=previous_price,
                    previous_currency="DKK" if previous_price is not None else None,
                    change_amount=change_amount,
                    change_percent=(
                        change_amount / previous_price * 100
                        if change_amount is not None and previous_price is not None
                        else None
                    ),
                    change_kind=(
                        ChangeKind.DECREASE if previous_price is not None else ChangeKind.INITIAL
                    ),
                )
            )
        target.current_price = Decimal("80.00")
        target.current_currency = "DKK"
        target.current_availability = Availability.IN_STOCK
        target.current_observed_at = now - timedelta(minutes=20)
        target.last_attempt_at = now - timedelta(minutes=20)
        target.last_success_at = now - timedelta(minutes=20)
        target.consecutive_failures = 0
        health = session.get(ScraperHealth, target.competitor_id)
        assert health is not None
        health.status = HealthStatus.HEALTHY
        health.last_attempt_at = target.last_attempt_at
        health.last_success_at = target.last_success_at
        session.commit()


def test_dashboard_read_models_match_the_frontend_contract(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client(session_factory, tmp_path) as http:
        customer, target = _create_catalog(http)
        _record_prices(session_factory, str(target["id"]))
        base = f"/api/v1/customers/{customer['id']}/dashboard"

        overview_response = http.get(base)
        assert overview_response.status_code == 200, overview_response.text
        overview = overview_response.json()
        assert overview["totalProducts"] == 1
        assert overview["monitoredOffers"] == 1
        assert overview["priceChanges24h"] == 1
        assert overview["overpricedProducts"] == 1
        assert overview["cheapestProducts"] == 0
        assert overview["staleOrFailed"] == 0
        assert overview["freshness"]["status"] == "healthy"
        assert overview["freshness"]["healthyPercentage"] == 100
        assert overview["freshness"]["checkedLastHour"] == 1
        assert overview["recentEvents"][0]["eventType"] == "price_drop"
        assert overview["recentEvents"][0]["currency"] == "DKK"
        assert overview["largestGaps"][0]["differenceAmount"] == 20.0

        products_response = http.get(f"{base}/products")
        assert products_response.status_code == 200, products_response.text
        comparison = products_response.json()[0]
        assert comparison["product"]["customerPrice"] == 100.0
        assert comparison["cheapestPrice"] == 80.0
        assert comparison["customerRank"] == 2
        assert comparison["competitorOffers"][0]["inStock"] is True

        detail_response = http.get(f"{base}/products/{comparison['product']['id']}")
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert len(detail["history"]) == 4
        assert {point["sourceType"] for point in detail["history"]} == {
            "customer",
            "competitor",
        }
        assert detail["events"][0]["newPrice"] == 80.0

        competitors_response = http.get(f"{base}/competitors")
        assert competitors_response.status_code == 200, competitors_response.text
        competitor = competitors_response.json()[0]
        assert competitor["monitoredProducts"] == 1
        assert competitor["cheapestProducts"] == 1
        assert competitor["successRate"] == 100

        health_response = http.get(f"{base}/health")
        assert health_response.status_code == 200, health_response.text
        health = health_response.json()
        assert health["healthyMonitors"] == 1
        assert health["staleMonitors"] == 0
        assert health["failedChecks"] == 0
        assert health["sites"][0]["status"] == "healthy"


def test_dashboard_is_customer_scoped(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client(session_factory, tmp_path) as http:
        customer, _ = _create_catalog(http)
        other = http.post(
            "/api/v1/customers",
            json={
                "name": "Other Shop",
                "slug": "other-shop",
                "webshop_url": "https://other.example.com",
            },
        ).json()
        product_id = http.get(f"/api/v1/customers/{customer['id']}/dashboard/products").json()[0][
            "product"
        ]["id"]

        response = http.get(f"/api/v1/customers/{other['id']}/dashboard/products/{product_id}")
        assert response.status_code == 404


def test_empty_customer_has_an_explicit_stale_dashboard(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client(session_factory, tmp_path) as http:
        customer = http.post(
            "/api/v1/customers",
            json={
                "name": "Empty Shop",
                "slug": "empty-shop",
                "webshop_url": "https://empty.example.com",
            },
        ).json()
        response = http.get(f"/api/v1/customers/{customer['id']}/dashboard")
        assert response.status_code == 200
        assert response.json()["freshness"] == {
            "status": "stale",
            "lastSuccessfulUpdate": None,
            "healthyPercentage": 0,
            "checkedLastHour": 0,
        }
