from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from price_monitor.db import (
    Base,
    Competitor,
    CompetitorProduct,
    Customer,
    PriceHistory,
    Product,
    RepairAttempt,
    ScrapeResult,
    ScraperHealth,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from price_monitor.db.session import SessionFactory
from price_monitor.domain.enums import (
    Availability,
    ChangeKind,
    FailureKind,
    FetchMode,
    HealthStatus,
    RepairStatus,
    ResultStatus,
)


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sessions(db_engine: Engine) -> SessionFactory:
    return create_session_factory(db_engine)


def _catalog(session: Session) -> tuple[Customer, Competitor, Product, CompetitorProduct]:
    customer = Customer(
        name="Demo Store",
        slug="demo-store",
        webshop_url="https://shop.example",
        default_currency="EUR",
        timezone="Europe/Copenhagen",
    )
    competitor = Competitor(
        customer=customer,
        name="Competitor One",
        base_url="https://competitor.example",
        adapter_key="competitor_one",
        expected_currency="EUR",
    )
    product = Product(
        customer=customer,
        name="A monitored product",
        sku="SKU-1",
        customer_product_url=None,
        current_own_price=Decimal("24.9500"),
        currency="EUR",
    )
    target = CompetitorProduct(
        product=product,
        competitor=competitor,
        product_url="https://competitor.example/products/sku-1",
        expected_name="A monitored product",
        expected_currency="EUR",
        minimum_valid_price=Decimal("1.00"),
        maximum_valid_price=Decimal("1000.00"),
    )
    session.add(customer)
    session.flush()
    return customer, competitor, product, target


def test_metadata_contains_all_eight_domain_tables(db_engine: Engine) -> None:
    assert set(inspect(db_engine).get_table_names()) == {
        "competitor_products",
        "competitors",
        "customers",
        "price_history",
        "products",
        "repair_attempts",
        "scrape_results",
        "scraper_health",
    }


def test_complete_model_graph_round_trips_typed_values(sessions: SessionFactory) -> None:
    observed_at = datetime(2026, 9, 6, 10, 30, tzinfo=UTC)

    with sessions() as session:
        customer, competitor, product, target = _catalog(session)
        result = ScrapeResult(
            run_key="demo-run-1",
            competitor_product=target,
            status=ResultStatus.SUCCEEDED,
            observed_at=observed_at,
            finished_at=observed_at,
            duration_ms=125,
            scraper_revision="rev-1",
            fetch_mode=FetchMode.HTTP,
            http_status=200,
            observed_name="A monitored product",
            price=Decimal("19.9900"),
            currency="EUR",
            availability=Availability.IN_STOCK,
            validation_errors=[],
            extraction_evidence={"price": {"source": "css", "selector": ".price"}},
            html_artifact_uri="artifacts/demo-run-1.html.gz",
            html_sha256="a" * 64,
        )
        history = PriceHistory(
            competitor_product=target,
            scrape_result=result,
            observed_at=observed_at,
            price=Decimal("19.9900"),
            currency="EUR",
            availability=Availability.IN_STOCK,
            change_kind=ChangeKind.INITIAL,
        )
        health = ScraperHealth(
            competitor=competitor,
            status=HealthStatus.HEALTHY,
            last_attempt_at=observed_at,
            last_success_at=observed_at,
            last_scrape_result=result,
        )
        repair = RepairAttempt(
            competitor=competitor,
            trigger_scrape_result=result,
            status=RepairStatus.QUEUED,
            failure_signature="fixture-selector-missing",
            baseline_revision="rev-1",
            changed_files=["src/price_monitor/scrapers/sites/demo.py"],
            test_report={"passed": 4},
            validation_report={"accepted": True},
        )
        session.add_all([history, health, repair])
        session.commit()
        ids = (customer.id, competitor.id, product.id, target.id, result.id, repair.id)

    with sessions() as session:
        stored = session.scalars(select(ScrapeResult)).one()
        assert isinstance(stored.id, uuid.UUID)
        assert stored.price == Decimal("19.9900")
        assert isinstance(stored.price, Decimal)
        assert stored.status is ResultStatus.SUCCEEDED
        assert stored.availability is Availability.IN_STOCK
        assert stored.observed_at == observed_at
        assert stored.observed_at is not None
        assert stored.observed_at.utcoffset() == UTC.utcoffset(observed_at)
        assert stored.extraction_evidence["price"]["selector"] == ".price"
        assert stored.price_history is not None
        assert stored.price_history.change_kind is ChangeKind.INITIAL
        assert stored.competitor_product.product.customer.slug == "demo-store"
        assert session.scalars(select(RepairAttempt)).one().changed_files == [
            "src/price_monitor/scrapers/sites/demo.py"
        ]
        assert ids == (
            stored.competitor_product.product.customer.id,
            stored.competitor_product.competitor.id,
            stored.competitor_product.product.id,
            stored.competitor_product.id,
            stored.id,
            session.scalars(select(RepairAttempt.id)).one(),
        )


def test_mutable_json_changes_are_persisted(sessions: SessionFactory) -> None:
    with sessions.begin() as session:
        _, competitor, _, target = _catalog(session)
        result = ScrapeResult(
            run_key="mutable-json",
            competitor_product=target,
            scraper_revision="rev-1",
            fetch_mode=FetchMode.HTTP,
        )
        repair = RepairAttempt(
            competitor=competitor,
            trigger_scrape_result=result,
            failure_signature="selector-missing",
            baseline_revision="rev-1",
        )
        session.add(repair)

    with sessions.begin() as session:
        stored_result = session.scalars(
            select(ScrapeResult).where(ScrapeResult.run_key == "mutable-json")
        ).one()
        stored_repair = session.scalars(select(RepairAttempt)).one()
        stored_result.validation_errors.append({"code": "missing-price"})
        stored_repair.test_report["passed"] = 3

    with sessions() as session:
        stored_result = session.scalars(select(ScrapeResult)).one()
        stored_repair = session.scalars(select(RepairAttempt)).one()
        assert stored_result.validation_errors == [{"code": "missing-price"}]
        assert stored_repair.test_report == {"passed": 3}


def test_only_one_active_scrape_is_allowed_per_target(sessions: SessionFactory) -> None:
    with sessions.begin() as session:
        _, _, _, target = _catalog(session)
        target_id = target.id
        session.add(
            ScrapeResult(
                run_key="active-1",
                competitor_product=target,
                status=ResultStatus.QUEUED,
                scraper_revision="rev-1",
                fetch_mode=FetchMode.HTTP,
            )
        )

    with sessions() as session:
        session.add(
            ScrapeResult(
                run_key="active-2",
                competitor_product_id=target_id,
                status=ResultStatus.RUNNING,
                scraper_revision="rev-1",
                fetch_mode=FetchMode.HTTP,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        first = session.scalars(
            select(ScrapeResult).where(ScrapeResult.run_key == "active-1")
        ).one()
        first.status = ResultStatus.SUCCEEDED
        session.commit()

        session.add(
            ScrapeResult(
                run_key="active-2",
                competitor_product_id=target_id,
                status=ResultStatus.RUNNING,
                scraper_revision="rev-1",
                fetch_mode=FetchMode.HTTP,
            )
        )
        session.commit()

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ScrapeResult)) == 2


def test_only_one_open_repair_is_allowed_per_competitor(sessions: SessionFactory) -> None:
    with sessions.begin() as session:
        _, competitor, _, _ = _catalog(session)
        competitor_id = competitor.id
        session.add(
            RepairAttempt(
                competitor=competitor,
                failure_signature="first",
                baseline_revision="rev-1",
            )
        )

    with sessions() as session:
        session.add(
            RepairAttempt(
                competitor_id=competitor_id,
                failure_signature="second",
                baseline_revision="rev-1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        first = session.scalars(select(RepairAttempt)).one()
        first.status = RepairStatus.REJECTED
        session.commit()
        session.add(
            RepairAttempt(
                competitor_id=competitor_id,
                failure_signature="second",
                baseline_revision="rev-1",
            )
        )
        session.commit()

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(RepairAttempt)) == 2


def test_database_constraints_reject_invalid_data(sessions: SessionFactory) -> None:
    with sessions() as session:
        customer = Customer(
            name="Invalid currency",
            slug="invalid-currency",
            webshop_url="https://shop.example",
            default_currency="eur",
        )
        session.add(customer)
        with pytest.raises(IntegrityError):
            session.commit()

    with sessions() as session:
        _, _, _, target = _catalog(session)
        target.minimum_valid_price = Decimal("20")
        target.maximum_valid_price = Decimal("10")
        with pytest.raises(IntegrityError):
            session.commit()


def test_naive_timestamps_are_rejected(sessions: SessionFactory) -> None:
    with sessions() as session:
        _, _, _, target = _catalog(session)
        session.add(
            ScrapeResult(
                run_key="naive-time",
                competitor_product=target,
                scraper_revision="rev-1",
                fetch_mode=FetchMode.HTTP,
                observed_at=datetime(2026, 9, 6, 10, 30),
            )
        )
        with pytest.raises(StatementError, match="timezone-aware"):
            session.commit()


def test_foreign_keys_cascade_owned_records(sessions: SessionFactory) -> None:
    with sessions.begin() as session:
        customer, competitor, _, target = _catalog(session)
        result = ScrapeResult(
            run_key="cascade",
            competitor_product=target,
            status=ResultStatus.FAILED,
            scraper_revision="rev-1",
            fetch_mode=FetchMode.HTTP,
            failure_kind=FailureKind.EXTRACTION,
        )
        session.add_all(
            [
                result,
                ScraperHealth(competitor=competitor, last_scrape_result=result),
                RepairAttempt(
                    competitor=competitor,
                    trigger_scrape_result=result,
                    failure_signature="cascade",
                    baseline_revision="rev-1",
                ),
            ]
        )
        customer_id = customer.id

    with sessions.begin() as session:
        customer = session.get(Customer, customer_id)
        assert customer is not None
        session.delete(customer)

    with sessions() as session:
        for model in (
            Customer,
            Competitor,
            Product,
            CompetitorProduct,
            ScrapeResult,
            ScraperHealth,
            RepairAttempt,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_session_scope_commits_and_rolls_back(sessions: SessionFactory) -> None:
    with session_scope(sessions) as session:
        session.add(
            Customer(
                name="Committed",
                slug="committed",
                webshop_url="https://committed.example",
            )
        )

    with pytest.raises(RuntimeError, match="abort"), session_scope(sessions) as session:
        session.add(
            Customer(
                name="Rolled back",
                slug="rolled-back",
                webshop_url="https://rolled-back.example",
            )
        )
        raise RuntimeError("abort")

    with sessions() as session:
        assert session.scalars(select(Customer.slug)).all() == ["committed"]
