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
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as client:
        yield client


@contextmanager
def _authenticated_client(
    factory: sessionmaker[Session], tmp_path: Path
) -> Generator[TestClient, None, None]:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        api_token="a-secure-test-token-that-is-long-enough",
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as client:
        yield client


def test_configured_bearer_token_protects_versioned_api(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _authenticated_client(session_factory, tmp_path) as http:
        homepage = http.get("/")
        assert homepage.status_code == 200
        assert homepage.headers["content-type"].startswith("text/html")
        assert "Price Monitor" in homepage.text
        assert "Service is online" in homepage.text
        assert 'href="/docs"' in homepage.text
        assert 'href="/healthz"' in homepage.text
        assert "a-secure-test-token-that-is-long-enough" not in homepage.text
        assert "<script" not in homepage.text
        assert "https://" not in homepage.text
        assert homepage.headers["content-security-policy"] == (
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        )
        assert homepage.headers["x-frame-options"] == "DENY"
        assert homepage.headers["x-content-type-options"] == "nosniff"
        assert homepage.headers["referrer-policy"] == "no-referrer"
        assert homepage.headers["cache-control"] == "no-store"
        assert http.get("/healthz").status_code == 200
        assert http.get("/readyz").status_code == 200
        assert http.get("/api/v1/customers").status_code == 401
        assert (
            http.get(
                "/api/v1/customers",
                headers={"Authorization": "Bearer a-wrong-token-that-is-long-enough"},
            ).status_code
            == 401
        )
        response = http.get(
            "/api/v1/customers",
            headers={"Authorization": "Bearer a-secure-test-token-that-is-long-enough"},
        )
        assert response.status_code == 200
        assert response.json() == []


def test_homepage_does_not_require_a_database_connection(tmp_path: Path) -> None:
    unavailable_database = tmp_path / "missing" / "price-monitor.db"
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{unavailable_database}",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
    )

    with TestClient(create_app(settings)) as http:
        response = http.get("/")

    assert response.status_code == 200
    assert "Service is online" in response.text
    assert not unavailable_database.exists()


def test_catalog_queue_and_read_api(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    with _client(session_factory, tmp_path) as http:
        assert http.get("/healthz").json() == {"status": "ok"}
        assert http.get("/readyz").json() == {"status": "ready"}
        assert http.get("/customers").status_code == 404

        customer_response = http.post(
            "/api/v1/customers",
            json={
                "name": "Example Shop",
                "slug": "example-shop",
                "webshop_url": "https://shop.example.com",
                "default_currency": "gbp",
            },
        )
        assert customer_response.status_code == 201, customer_response.text
        customer = customer_response.json()
        assert customer["default_currency"] == "GBP"

        competitor_response = http.post(
            f"/api/v1/customers/{customer['id']}/competitors",
            json={
                "name": "Books to Scrape",
                "base_url": "https://books.toscrape.com",
                "adapter_key": "books_to_scrape",
            },
        )
        assert competitor_response.status_code == 201, competitor_response.text
        competitor = competitor_response.json()
        assert competitor["active_scraper_revision"] == "1"

        product_response = http.post(
            f"/api/v1/customers/{customer['id']}/products",
            json={"name": "A Light in the Attic", "sku": "book-1"},
        )
        assert product_response.status_code == 201, product_response.text
        product = product_response.json()
        assert product["customer_product_url"] is None

        target_response = http.post(
            f"/api/v1/products/{product['id']}/competitor-products",
            json={
                "competitor_id": competitor["id"],
                "product_url": (
                    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
                ),
                "expected_currency": "GBP",
                "minimum_valid_price": "1.00",
                "maximum_valid_price": "500.00",
            },
        )
        assert target_response.status_code == 201, target_response.text
        target = target_response.json()

        queued_response = http.post(f"/api/v1/competitor-products/{target['id']}/scrapes")
        assert queued_response.status_code == 202, queued_response.text
        queued = queued_response.json()
        duplicate = http.post(f"/api/v1/competitor-products/{target['id']}/scrapes")
        assert duplicate.status_code == 202
        assert duplicate.json()["scrape_result_id"] == queued["scrape_result_id"]

        result = http.get(f"/api/v1/scrape-results/{queued['scrape_result_id']}")
        assert result.status_code == 200
        assert result.json()["status"] == "queued"
        assert http.get(f"/api/v1/competitors/{competitor['id']}/health").status_code == 200
        assert http.get(f"/api/v1/products/{product['id']}/offers").json()[0]["price"] is None


def test_api_enforces_tenant_and_adapter_host_boundaries(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _client(session_factory, tmp_path) as http:
        first = http.post(
            "/api/v1/customers",
            json={
                "name": "First",
                "slug": "first",
                "webshop_url": "https://first.example.com",
            },
        ).json()
        second = http.post(
            "/api/v1/customers",
            json={
                "name": "Second",
                "slug": "second",
                "webshop_url": "https://second.example.com",
            },
        ).json()
        invalid_site = http.post(
            f"/api/v1/customers/{first['id']}/competitors",
            json={
                "name": "Wrong Host",
                "base_url": "https://example.com",
                "adapter_key": "books_to_scrape",
            },
        )
        assert invalid_site.status_code == 422

        credentialed_site = http.post(
            f"/api/v1/customers/{first['id']}/competitors",
            json={
                "name": "Credentialed URL",
                "base_url": "https://user:password@books.toscrape.com",
                "adapter_key": "books_to_scrape",
            },
        )
        assert credentialed_site.status_code == 422

        competitor = http.post(
            f"/api/v1/customers/{first['id']}/competitors",
            json={
                "name": "Books",
                "base_url": "https://books.toscrape.com",
                "adapter_key": "books_to_scrape",
            },
        ).json()
        foreign_product = http.post(
            f"/api/v1/customers/{second['id']}/products",
            json={"name": "Foreign product"},
        ).json()
        cross_tenant = http.post(
            f"/api/v1/products/{foreign_product['id']}/competitor-products",
            json={
                "competitor_id": competitor["id"],
                "product_url": "https://books.toscrape.com/catalogue/item/index.html",
            },
        )
        assert cross_tenant.status_code == 422

        product = http.post(
            f"/api/v1/customers/{first['id']}/products",
            json={"name": "First product"},
        ).json()
        downgraded = http.post(
            f"/api/v1/products/{product['id']}/competitor-products",
            json={
                "competitor_id": competitor["id"],
                "product_url": "http://books.toscrape.com/catalogue/item/index.html",
            },
        )
        assert downgraded.status_code == 422
