from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.db import (
    Competitor,
    CompetitorProduct,
    Customer,
    PriceHistory,
    Product,
    RepairAttempt,
    ScrapeResult,
)
from price_monitor.domain.enums import Availability, FailureKind, FetchMode, ResultStatus
from price_monitor.domain.types import (
    ExtractedProduct,
    FieldEvidence,
    ValidationIssue,
    ValidationOutcome,
    utc_now,
)
from price_monitor.services.errors import LeaseLostError
from price_monitor.services.queue import ScrapeQueue
from price_monitor.services.results import ResultRecorder

pytestmark = pytest.mark.integration


def _seed(session: Session) -> CompetitorProduct:
    customer = Customer(
        name="Shop",
        slug="shop",
        webshop_url="https://shop.example.com",
        default_currency="GBP",
    )
    session.add(customer)
    session.flush()
    competitor = Competitor(
        customer_id=customer.id,
        name="Books",
        base_url="https://books.toscrape.com",
        adapter_key="books_to_scrape",
        active_scraper_revision="1",
        fetch_mode=FetchMode.HTTP,
        expected_currency="GBP",
    )
    product = Product(customer_id=customer.id, name="A Light in the Attic", sku="book")
    session.add_all((competitor, product))
    session.flush()
    target = CompetitorProduct(
        product_id=product.id,
        competitor_id=competitor.id,
        product_url=("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"),
        expected_name=product.name,
        expected_currency="GBP",
        minimum_valid_price=Decimal("1"),
        maximum_valid_price=Decimal("500"),
    )
    session.add(target)
    session.commit()
    return target


def _extracted(price: str) -> ExtractedProduct:
    context = f"A Light in the Attic £{price} In stock"
    return ExtractedProduct(
        name="A Light in the Attic",
        price=Decimal(price),
        currency="GBP",
        availability=Availability.IN_STOCK,
        product_url=("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"),
        evidence={
            "name": FieldEvidence(
                source="css", raw_value="A Light in the Attic", container_text=context
            ),
            "price": FieldEvidence(source="css", raw_value=f"£{price}", container_text=context),
            "currency": FieldEvidence(
                source="derived", raw_value=f"£{price}", container_text=context
            ),
        },
    )


def _claim(factory: sessionmaker[Session], target_id: UUID):  # type: ignore[no-untyped-def]
    queue = ScrapeQueue()
    with factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with factory() as session:
        claimed = queue.claim_next(session)
        session.commit()
    assert claimed is not None
    return claimed


def test_history_change_and_repair_threshold_are_transactional(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    del tmp_path
    with session_factory() as session:
        target = _seed(session)
        target_id = target.id
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        repair_failure_threshold=1,
        repair_minimum_distinct_targets=1,
        repair_cooldown_seconds=0,
    )
    recorder = ResultRecorder(settings)
    accepted = ValidationOutcome(accepted=True)

    first = _claim(session_factory, target_id)
    with session_factory() as session:
        _, initial = recorder.record_success(
            session,
            result_id=first.result_id,
            lease_token=first.lease_token,
            extracted=_extracted("51.77"),
            validation=accepted,
            duration_ms=10,
            http_status=200,
            html_artifact_uri="html/books/first.html.gz",
            html_sha256="a" * 64,
        )
        session.commit()
        assert initial.change_kind == "initial"

    second = _claim(session_factory, target_id)
    with session_factory() as session:
        _, changed = recorder.record_success(
            session,
            result_id=second.result_id,
            lease_token=second.lease_token,
            extracted=_extracted("47.99"),
            validation=accepted,
            duration_ms=10,
            http_status=200,
            html_artifact_uri="html/books/second.html.gz",
            html_sha256="b" * 64,
        )
        session.commit()
        assert changed.previous_price == Decimal("51.7700")
        assert changed.change_kind == "decrease"
        assert changed.change_amount == Decimal("-3.7800")

    failed = _claim(session_factory, target_id)
    invalid = ValidationOutcome(
        accepted=False,
        issues=(
            ValidationIssue(
                code="price_missing",
                message="price selector no longer exists",
                severity="error",
                failure_kind=FailureKind.EXTRACTION,
            ),
        ),
    )
    with session_factory() as session:
        _, repair = recorder.record_invalid(
            session,
            result_id=failed.result_id,
            lease_token=failed.lease_token,
            extracted=None,
            validation=invalid,
            duration_ms=10,
            http_status=200,
            html_artifact_uri="html/books/failure.html.gz",
            html_sha256="c" * 64,
        )
        session.commit()
        assert repair is not None

    with session_factory() as session:
        assert session.scalar(select(func.count(PriceHistory.id))) == 2
        assert session.scalar(select(func.count(RepairAttempt.id))) == 1
        stored_target = session.get(CompetitorProduct, target_id)
        assert stored_target is not None
        assert stored_target.current_price == Decimal("47.9900")
        assert stored_target.consecutive_failures == 1


def test_nonrepairable_failure_and_expired_lease_reclaim(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        target = _seed(session)
        target_id = target.id
    queue = ScrapeQueue(lease_seconds=60)
    with session_factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with session_factory() as session:
        first_claim = queue.claim_next(session)
        assert first_claim is not None
        result = session.get(ScrapeResult, first_claim.result_id)
        assert result is not None
        result.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    with session_factory() as session:
        second_claim = queue.claim_next(session)
        session.commit()
    assert second_claim is not None
    assert second_claim.lease_token != first_claim.lease_token

    recorder = ResultRecorder(
        Settings(
            environment="test",
            database_url="sqlite+pysqlite:///:memory:",
            repair_failure_threshold=1,
            repair_minimum_distinct_targets=1,
            repair_cooldown_seconds=0,
        )
    )
    with session_factory() as session:
        _, repair = recorder.record_failure(
            session,
            result_id=second_claim.result_id,
            lease_token=second_claim.lease_token,
            failure_kind=FailureKind.RATE_LIMITED,
            failure_code="FETCH_RATE_LIMITED",
            message="upstream returned 429",
            duration_ms=5,
            status=ResultStatus.FAILED,
            http_status=429,
        )
        session.commit()
        assert repair is None


def test_lease_renewal_requires_current_unexpired_owner(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        target_id = _seed(session).id

    queue = ScrapeQueue(lease_seconds=60)
    with session_factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with session_factory() as session:
        claimed = queue.claim_next(session)
        session.commit()
    assert claimed is not None

    with session_factory() as session:
        renewed_until = queue.renew_lease(
            session,
            result_id=claimed.result_id,
            lease_token=claimed.lease_token,
        )
        session.commit()
    assert renewed_until is not None
    assert renewed_until > claimed.lease_expires_at

    with session_factory() as session:
        stale_renewal = queue.renew_lease(
            session,
            result_id=claimed.result_id,
            lease_token=uuid4(),
        )
        session.commit()
    assert stale_renewal is None

    with session_factory() as session:
        result = session.get(ScrapeResult, claimed.result_id)
        assert result is not None
        result.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.commit()
    with session_factory() as session:
        expired_renewal = queue.renew_lease(
            session,
            result_id=claimed.result_id,
            lease_token=claimed.lease_token,
        )
        session.commit()
    assert expired_renewal is None


def test_result_recorder_cannot_finalize_an_expired_lease(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        target_id = _seed(session).id

    queue = ScrapeQueue(lease_seconds=60)
    with session_factory() as session:
        queue.enqueue_target(session, target_id)
        session.commit()
    with session_factory() as session:
        claimed = queue.claim_next(session)
        session.commit()
    assert claimed is not None

    with session_factory() as session:
        result = session.get(ScrapeResult, claimed.result_id)
        assert result is not None
        result.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.commit()

    recorder = ResultRecorder(Settings(environment="test"))
    with session_factory() as session:
        with pytest.raises(LeaseLostError, match="expired"):
            recorder.record_success(
                session,
                result_id=claimed.result_id,
                lease_token=claimed.lease_token,
                extracted=_extracted("51.77"),
                validation=ValidationOutcome(accepted=True),
                duration_ms=10,
                http_status=200,
                html_artifact_uri="html/books/expired.html.gz",
                html_sha256="e" * 64,
            )
        session.rollback()

    with session_factory() as session:
        result = session.get(ScrapeResult, claimed.result_id)
        assert result is not None
        assert result.status == ResultStatus.RUNNING
        assert session.scalar(select(func.count(PriceHistory.id))) == 0
