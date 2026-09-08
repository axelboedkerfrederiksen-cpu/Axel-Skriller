from __future__ import annotations

import re
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
        assert "Loading prices" in homepage.text
        assert 'href="/products"' in homepage.text
        assert 'href="/competitors"' in homepage.text
        assert 'href="/alerts"' in homepage.text
        assert 'href="/static/price-monitor/app.css"' in homepage.text
        assert 'src="/static/price-monitor/app.js"' in homepage.text
        assert "Competitors" in homepage.text
        assert 'id="service-status"' in homepage.text
        assert 'href="/healthz"' not in homepage.text
        assert "a-secure-test-token-that-is-long-enough" not in homepage.text
        assert "http://" not in homepage.text
        assert "https://" not in homepage.text
        assert "gradient(" not in homepage.text
        assert "backdrop-filter" not in homepage.text
        assert homepage.headers["content-security-policy"] == (
            "default-src 'none'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        assert homepage.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=()"
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


def test_adapter_catalog_is_safe_discoverable_and_authenticated(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    expected = [
        {
            "key": "books_to_scrape",
            "display_name": "Books to Scrape",
            "allowed_hosts": ["books.toscrape.com"],
            "fetch_mode": "http",
        }
    ]
    with _client(session_factory, tmp_path) as http:
        response = http.get("/api/v1/adapters")
        schema = http.get("/openapi.json").json()

    assert response.status_code == 200
    assert response.json() == expected
    assert "selector" not in response.text
    assert "revision" not in response.text
    operation = schema["paths"]["/api/v1/adapters"]["get"]
    assert operation["security"] == [{"HTTPBearer": []}]

    token = "a-secure-test-token-that-is-long-enough"
    with _authenticated_client(session_factory, tmp_path) as http:
        assert http.get("/api/v1/adapters").status_code == 401
        authenticated = http.get(
            "/api/v1/adapters",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert authenticated.status_code == 200
    assert authenticated.json() == expected


def test_operational_ui_routes_share_one_secure_responsive_application_shell(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _client(session_factory, tmp_path) as http:
        routes = (
            "/",
            "/products",
            "/products/new",
            "/products/00000000-0000-0000-0000-000000000001",
            "/competitors",
            "/alerts",
        )
        responses = [http.get(route) for route in routes]
        styles = http.get("/static/price-monitor/app.css")
        script = http.get("/static/price-monitor/app.js")
        openapi = http.get("/openapi.json").json()

    assert all(response.status_code == 200 for response in responses)
    assert all(response.text == responses[0].text for response in responses)
    assert all(response.headers["cache-control"] == "no-store" for response in responses)
    assert all(response.headers["x-frame-options"] == "DENY" for response in responses)
    assert '<meta name="viewport"' in responses[0].text
    assert 'class="skip-link"' in responses[0].text
    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert "localStorage" not in script.text
    assert "sessionStorage" not in script.text
    for route in routes:
        assert route not in openapi["paths"]


def test_api_workspace_matches_the_price_monitor_ui_and_links_home(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _authenticated_client(session_factory, tmp_path) as http:
        response = http.get("/docs")
        redoc = http.get("/redoc")
        homepage = http.get("/")
        trailing_slash = http.get("/docs/", follow_redirects=False)
        oauth_redirect = http.get("/docs/oauth2-redirect")

    assert response.status_code == 200
    assert redoc.status_code == 200
    assert "ReDoc" in redoc.text
    assert response.headers["content-type"].startswith("text/html")
    assert '<meta name="viewport"' in response.text
    assert 'data-ui="price-monitor-api-workspace"' in response.text
    assert "API workspace · Price Monitor" in response.text
    assert "Back to homepage" in response.text
    assert 'href="/" aria-label="Price Monitor homepage"' in response.text
    assert 'href="/healthz"' in response.text
    assert 'url: "/openapi.json"' in response.text
    assert "swagger-ui-dist@5.32.15/swagger-ui-bundle.js" in response.text
    assert "swagger-ui-dist@5.32.15/swagger-ui.css" in response.text
    assert 'integrity="sha384-' in response.text
    assert "Price Monitor API - Swagger UI" not in response.text
    assert "fastapi.tiangolo.com/img/favicon.png" not in response.text
    assert "gradient(" not in response.text
    assert "backdrop-filter" not in response.text
    assert homepage.status_code == 200
    assert "Price Monitor" in homepage.text
    assert trailing_slash.status_code == 307
    assert trailing_slash.headers["location"] == "http://testserver/docs"
    assert oauth_redirect.status_code == 200


def test_api_workspace_uses_fresh_nonces_and_never_exposes_the_api_token(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    token = "a-secure-test-token-that-is-long-enough"
    with _authenticated_client(session_factory, tmp_path) as http:
        first = http.get("/docs")
        second = http.get("/docs")
        openapi_response = http.get("/openapi.json")

    first_policy = first.headers["content-security-policy"]
    second_policy = second.headers["content-security-policy"]
    first_nonce = re.search(r"script-src 'nonce-([^']+)'", first_policy)
    second_nonce = re.search(r"script-src 'nonce-([^']+)'", second_policy)
    assert first_nonce is not None
    assert second_nonce is not None
    assert first_nonce.group(1) != second_nonce.group(1)
    assert f'<script nonce="{first_nonce.group(1)}">' in first.text
    assert "script-src 'unsafe-inline'" not in first_policy
    assert "script-src 'nonce-" in first_policy
    assert "https://cdn.jsdelivr.net" in first_policy
    assert "connect-src 'self'" in first_policy
    assert "img-src 'self' data:" in first_policy
    assert "base-uri 'none'" in first_policy
    assert "form-action 'none'" in first_policy
    assert "frame-ancestors 'none'" in first_policy
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-frame-options"] == "DENY"
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers["referrer-policy"] == "no-referrer"
    assert token not in first.text
    assert token not in openapi_response.text


def test_custom_api_workspace_does_not_change_the_openapi_contract(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _authenticated_client(session_factory, tmp_path) as http:
        schema = http.get("/openapi.json").json()

    assert schema["info"]["title"] == "Price Monitor API"
    assert schema["info"]["version"] == "0.1.0"
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    for ui_path in (
        "/",
        "/docs",
        "/products",
        "/products/new",
        "/products/{product_id}",
        "/competitors",
        "/alerts",
        "/session",
        "/healthz",
        "/readyz",
    ):
        assert ui_path not in schema["paths"]

    create_product = schema["paths"]["/api/v1/customers/{customer_id}/products"]["post"]
    assert create_product["security"] == [{"HTTPBearer": []}]
    assert create_product["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProductCreate"
    }
    assert create_product["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProductRead"
    }


def test_homepage_does_not_require_a_database_connection(tmp_path: Path) -> None:
    unavailable_database = tmp_path / "missing" / "price-monitor.db"
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{unavailable_database}",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
    )

    with TestClient(create_app(settings)) as http:
        homepage = http.get("/")
        add_product = http.get("/products/new")

    assert homepage.status_code == 200
    assert "Loading prices" in homepage.text
    assert add_product.status_code == 200
    assert "Loading prices" in add_product.text
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
