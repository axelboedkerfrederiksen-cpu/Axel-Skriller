from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.db import CompetitorProduct
from price_monitor.db.session import get_db_session
from price_monitor.domain.enums import Availability, FailureKind
from price_monitor.domain.types import ExtractedProduct, ValidationOutcome
from price_monitor.main import create_app
from price_monitor.services.queue import ScrapeQueue
from price_monitor.services.results import ResultRecorder

pytestmark = pytest.mark.integration


@contextmanager
def _client(
    factory: sessionmaker[Session],
    tmp_path: Path,
    *,
    api_token: str | None = None,
) -> Generator[TestClient, None, None]:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        api_token=api_token,
        respect_robots_txt=False,
    )
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    with TestClient(app) as http:
        yield http


def _catalog(http: TestClient, *, slug: str = "shop") -> dict[str, dict[str, object]]:
    customer_response = http.post(
        "/api/v1/customers",
        json={
            "name": slug.title(),
            "slug": slug,
            "webshop_url": f"https://{slug}.example.com",
            "default_currency": "GBP",
        },
    )
    assert customer_response.status_code == 201
    customer = customer_response.json()

    competitor_response = http.post(
        f"/api/v1/customers/{customer['id']}/competitors",
        json={
            "name": "Books to Scrape",
            "base_url": "https://books.toscrape.com",
            "adapter_key": "books_to_scrape",
            "expected_currency": "GBP",
        },
    )
    assert competitor_response.status_code == 201
    competitor = competitor_response.json()

    product_response = http.post(
        f"/api/v1/customers/{customer['id']}/products",
        json={"name": "A Light in the Attic", "sku": f"{slug}-book"},
    )
    assert product_response.status_code == 201
    product = product_response.json()

    target_response = http.post(
        f"/api/v1/products/{product['id']}/competitor-products",
        json={
            "competitor_id": competitor["id"],
            "product_url": (
                "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
            ),
            "expected_currency": "GBP",
            "minimum_valid_price": "1",
            "maximum_valid_price": "500",
        },
    )
    assert target_response.status_code == 201
    return {
        "customer": customer,
        "competitor": competitor,
        "product": product,
        "target": target_response.json(),
    }


def _record_price(
    factory: sessionmaker[Session],
    target_id: UUID,
    price: str,
    settings: Settings,
) -> None:
    queue = ScrapeQueue()
    with factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with factory() as session:
        claim = queue.claim_next(session)
        session.commit()
    assert claim is not None

    extracted = ExtractedProduct(
        name="A Light in the Attic",
        price=Decimal(price),
        currency="GBP",
        availability=Availability.IN_STOCK,
        product_url=("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"),
        evidence={},
    )
    with factory() as session:
        ResultRecorder(settings).record_success(
            session,
            result_id=claim.result_id,
            lease_token=claim.lease_token,
            extracted=extracted,
            validation=ValidationOutcome(accepted=True),
            duration_ms=12,
            http_status=200,
            html_artifact_uri="html/books/accepted.html.gz",
            html_sha256="a" * 64,
        )
        session.commit()


def _record_failure(
    factory: sessionmaker[Session],
    target_id: UUID,
    settings: Settings,
) -> None:
    queue = ScrapeQueue()
    with factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with factory() as session:
        claim = queue.claim_next(session)
        session.commit()
    assert claim is not None
    with factory() as session:
        ResultRecorder(settings).record_failure(
            session,
            result_id=claim.result_id,
            lease_token=claim.lease_token,
            failure_kind=FailureKind.TRANSPORT,
            failure_code="FETCH_TRANSPORT",
            message="upstream connection failed",
            duration_ms=12,
        )
        session.commit()


def test_alert_rule_crud_and_trusted_history_evaluation(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        respect_robots_txt=False,
    )
    with _client(session_factory, tmp_path) as http:
        catalog = _catalog(http)
        customer_id = catalog["customer"]["id"]
        product_id = catalog["product"]["id"]
        target_id = UUID(str(catalog["target"]["id"]))

        created_response = http.post(
            f"/api/v1/customers/{customer_id}/alert-rules",
            json={
                "product_id": product_id,
                "direction": "decrease",
                "threshold_percent": "5",
            },
        )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        assert created["customer_id"] == customer_id
        assert created["product_id"] == product_id
        assert created["direction"] == "decrease"
        assert Decimal(created["threshold_percent"]) == Decimal("5")
        assert created["is_active"] is True
        assert created["evaluation"] == {
            "state": "waiting",
            "last_checked_at": None,
            "last_triggered_at": None,
            "competitor_product_id": None,
            "price": None,
            "previous_price": None,
            "currency": None,
            "change_percent": None,
        }
        rule_id = created["id"]

        _record_price(session_factory, target_id, "100", settings)
        clear = http.get(f"/api/v1/alert-rules/{rule_id}")
        assert clear.status_code == 200
        assert clear.json()["evaluation"]["state"] == "clear"
        assert clear.json()["evaluation"]["last_checked_at"] is not None

        _record_price(session_factory, target_id, "90", settings)
        triggered_response = http.get(f"/api/v1/alert-rules/{rule_id}")
        assert triggered_response.status_code == 200
        triggered = triggered_response.json()["evaluation"]
        assert triggered["state"] == "triggered"
        assert triggered["last_checked_at"] == triggered["last_triggered_at"]
        assert triggered["competitor_product_id"] == str(target_id)
        assert Decimal(triggered["price"]) == Decimal("90")
        assert Decimal(triggered["previous_price"]) == Decimal("100")
        assert triggered["currency"] == "GBP"
        assert Decimal(triggered["change_percent"]) == Decimal("-10")

        trusted_timestamp = triggered["last_checked_at"]
        _record_failure(session_factory, target_id, settings)
        after_failure = http.get(f"/api/v1/alert-rules/{rule_id}").json()["evaluation"]
        assert after_failure["state"] == "triggered"
        assert after_failure["last_checked_at"] == trusted_timestamp
        with session_factory() as session:
            target = session.get(CompetitorProduct, target_id)
            assert target is not None
            assert target.current_price == Decimal("90")
            assert target.consecutive_failures == 1

        disabled_response = http.patch(
            f"/api/v1/alert-rules/{rule_id}",
            json={"is_active": False},
        )
        assert disabled_response.status_code == 200
        assert disabled_response.json()["evaluation"]["state"] == "disabled"

        raised_threshold = http.patch(
            f"/api/v1/alert-rules/{rule_id}",
            json={"is_active": True, "threshold_percent": "20"},
        )
        assert raised_threshold.status_code == 200
        assert raised_threshold.json()["evaluation"]["state"] == "clear"

        listed = http.get(f"/api/v1/customers/{customer_id}/alert-rules")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [rule_id]

        deleted = http.delete(f"/api/v1/alert-rules/{rule_id}")
        assert deleted.status_code == 204
        assert deleted.content == b""
        assert http.get(f"/api/v1/alert-rules/{rule_id}").status_code == 404
        assert http.get(f"/api/v1/customers/{customer_id}/alert-rules").json() == []


def test_alert_rules_validate_thresholds_and_tenant_ownership(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    with _client(session_factory, tmp_path) as http:
        first = _catalog(http, slug="first")
        second = _catalog(http, slug="second")
        customer_id = first["customer"]["id"]
        foreign_product_id = second["product"]["id"]

        cross_tenant = http.post(
            f"/api/v1/customers/{customer_id}/alert-rules",
            json={
                "product_id": foreign_product_id,
                "direction": "either",
                "threshold_percent": "5",
            },
        )
        assert cross_tenant.status_code == 422

        missing_product = http.post(
            f"/api/v1/customers/{customer_id}/alert-rules",
            json={
                "product_id": str(uuid4()),
                "direction": "increase",
                "threshold_percent": "5",
            },
        )
        assert missing_product.status_code == 404

        for payload in (
            {"product_id": first["product"]["id"], "direction": "decrease", "threshold_percent": 0},
            {
                "product_id": first["product"]["id"],
                "direction": "decrease",
                "threshold_percent": 10_001,
            },
            {"product_id": first["product"]["id"], "direction": "sideways", "threshold_percent": 5},
        ):
            assert (
                http.post(f"/api/v1/customers/{customer_id}/alert-rules", json=payload).status_code
                == 422
            )

        valid = http.post(
            f"/api/v1/customers/{customer_id}/alert-rules",
            json={
                "product_id": first["product"]["id"],
                "direction": "either",
                "threshold_percent": 5,
            },
        ).json()
        assert http.patch(f"/api/v1/alert-rules/{valid['id']}", json={}).status_code == 422
        for field in ("direction", "threshold_percent", "is_active"):
            assert (
                http.patch(
                    f"/api/v1/alert-rules/{valid['id']}",
                    json={field: None},
                ).status_code
                == 422
            )


def test_alert_directions_match_only_accepted_changes_at_or_above_threshold(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        respect_robots_txt=False,
    )
    with _client(session_factory, tmp_path) as http:
        catalog = _catalog(http)
        customer_id = catalog["customer"]["id"]
        product_id = catalog["product"]["id"]
        target_id = UUID(str(catalog["target"]["id"]))
        rule_ids: dict[str, str] = {}
        for direction, threshold in (("decrease", "10"), ("increase", "10"), ("either", "10")):
            response = http.post(
                f"/api/v1/customers/{customer_id}/alert-rules",
                json={
                    "product_id": product_id,
                    "direction": direction,
                    "threshold_percent": threshold,
                },
            )
            assert response.status_code == 201
            rule_ids[direction] = response.json()["id"]

        _record_price(session_factory, target_id, "100", settings)
        _record_price(session_factory, target_id, "90", settings)
        assert (
            http.get(f"/api/v1/alert-rules/{rule_ids['decrease']}").json()["evaluation"]["state"]
            == "triggered"
        )
        assert (
            http.get(f"/api/v1/alert-rules/{rule_ids['increase']}").json()["evaluation"]["state"]
            == "clear"
        )
        assert (
            http.get(f"/api/v1/alert-rules/{rule_ids['either']}").json()["evaluation"]["state"]
            == "triggered"
        )

        _record_price(session_factory, target_id, "99", settings)
        increase = http.get(f"/api/v1/alert-rules/{rule_ids['increase']}").json()["evaluation"]
        assert increase["state"] == "triggered"
        assert Decimal(increase["change_percent"]) == Decimal("10")


def test_alert_rule_api_uses_the_existing_bearer_guard(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    token = "a-secure-test-token-that-is-long-enough"
    with _client(session_factory, tmp_path, api_token=token) as http:
        response = http.get(f"/api/v1/customers/{uuid4()}/alert-rules")
        authorized = http.get(
            f"/api/v1/customers/{uuid4()}/alert-rules",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert authorized.status_code == 404
    assert token not in response.text
