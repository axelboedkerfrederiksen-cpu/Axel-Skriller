from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from price_monitor.config import Settings
from price_monitor.db import (
    CompetitorProduct,
    Customer,
    PriceHistory,
    Product,
    ScrapeResult,
    create_db_engine,
    create_schema,
    create_session_factory,
)
from price_monitor.domain.enums import ResultStatus
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.development_seed import seed_development_workspace

pytestmark = pytest.mark.integration


def test_development_seed_is_real_idempotent_and_preserves_trusted_price(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        respect_robots_txt=False,
    )
    engine = create_db_engine(settings.database_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    registry = AdapterRegistry(settings.adapter_runtime_root)
    try:
        assert asyncio.run(
            seed_development_workspace(
                settings=settings,
                session_factory=factory,
                registry=registry,
            )
        )
        assert not asyncio.run(
            seed_development_workspace(
                settings=settings,
                session_factory=factory,
                registry=registry,
            )
        )

        with factory() as session:
            customer_id = session.scalar(
                select(Customer.id).where(Customer.slug == "price-monitor-development")
            )
            assert customer_id is not None
            session.add(Product(customer_id=customer_id, name="User-added product", sku="USER-1"))
            session.commit()

        assert not asyncio.run(
            seed_development_workspace(
                settings=settings,
                session_factory=factory,
                registry=registry,
            )
        )

        with factory() as session:
            customer = session.scalar(
                select(Customer).where(Customer.slug == "price-monitor-development")
            )
            assert customer is not None
            products = list(
                session.scalars(
                    select(Product)
                    .where(Product.customer_id == customer.id)
                    .order_by(Product.name)
                )
            )
            assert [product.name for product in products] == [
                "A Light in the Attic",
                "The Secret Garden",
                "Tipping the Velvet",
                "User-added product",
            ]
            light = next(product for product in products if product.sku == "BK-1000")
            target = session.scalar(
                select(CompetitorProduct).where(CompetitorProduct.product_id == light.id)
            )
            assert target is not None
            assert target.current_price == Decimal("47.9900")
            assert target.consecutive_failures == 1
            assert target.last_success_at == target.current_observed_at

            history_count = session.scalar(select(func.count(PriceHistory.id)))
            result_count = session.scalar(select(func.count(ScrapeResult.id)))
            failed_count = session.scalar(
                select(func.count(ScrapeResult.id)).where(
                    ScrapeResult.status == ResultStatus.FAILED
                )
            )
            assert history_count == 3
            assert result_count == 4
            assert failed_count == 1
    finally:
        engine.dispose()


def test_development_seed_is_forbidden_in_preview(tmp_path: Path) -> None:
    settings = Settings(
        environment="preview",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        api_token="a-secure-test-token-that-is-long-enough",
    )
    engine = create_db_engine(settings.database_url)
    create_schema(engine)
    factory = create_session_factory(engine)
    registry = AdapterRegistry(settings.adapter_runtime_root)
    try:
        with pytest.raises(ValueError, match="forbidden"):
            asyncio.run(
                seed_development_workspace(
                    settings=settings,
                    session_factory=factory,
                    registry=registry,
                )
            )
    finally:
        engine.dispose()
