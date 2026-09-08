from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from price_monitor.api.schemas import (
    CompetitorCreate,
    CompetitorProductCreate,
    CustomerCreate,
    ProductCreate,
)
from price_monitor.config import Settings
from price_monitor.db.models import CompetitorProduct, Customer, PriceHistory, Product, ScrapeResult
from price_monitor.db.session import SessionFactory, session_scope
from price_monitor.domain.enums import FetchMode, ResultStatus
from price_monitor.domain.types import FetchedPage, utc_now
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.catalog import CatalogService
from price_monitor.services.queue import ClaimedScrape
from price_monitor.services.worker import ScrapeWorker

_SEED_SLUG = "price-monitor-development"
_SEED_SKUS = ("BK-1000", "BK-0999", "BK-NEW")
_LIGHT_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
_VELVET_URL = "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"


class _FixtureWorker(ScrapeWorker):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.pages: list[FetchedPage] = []

    async def _fetch(self, claimed: ClaimedScrape) -> FetchedPage:
        del claimed
        if not self.pages:
            raise RuntimeError("development fixture queue is empty")
        return self.pages.pop(0)

    async def process_target(self, target_id: UUID, page: FetchedPage) -> None:
        """Claim only the just-enqueued seed job, never an unrelated queued job."""

        with session_scope(self.session_factory) as session:
            queued = self.queue.enqueue_target(session, target_id)
            claimed = self.queue.claim_next(session)
            if claimed is None or claimed.result_id != queued.id:
                raise RuntimeError("another queued job prevents safe development seeding")
        self.pages.append(page)
        await self._process_with_renewing_lease(claimed)


async def seed_development_workspace(
    *,
    settings: Settings,
    session_factory: SessionFactory,
    registry: AdapterRegistry,
) -> bool:
    """Create an idempotent, offline workspace only in explicitly safe environments."""

    if settings.environment not in {"development", "test"}:
        raise ValueError("development seed data is forbidden in hosted environments")

    with session_factory() as session:
        existing = session.scalar(select(Customer).where(Customer.slug == _SEED_SLUG))
        if existing is not None:
            if _seed_is_complete(session, existing.id):
                return False
            raise ValueError("existing development seed is incomplete; no data was changed")
        if (session.scalar(select(func.count(Customer.id))) or 0) > 0:
            raise ValueError("development seed requires an empty database")

    fixtures = Path(__file__).resolve().parent.parent / "demo_fixtures" / "books_to_scrape"
    now = utc_now()
    pages = (
        _fixture_page(
            fixtures / "a-light-in-the-attic.html",
            _LIGHT_URL,
            fetched_at=now - timedelta(minutes=38),
        ),
        _fixture_page(
            fixtures / "a-light-price-change.html",
            _LIGHT_URL,
            fetched_at=now - timedelta(minutes=5),
        ),
        _fixture_page(
            fixtures / "a-light-broken-selector.html",
            _LIGHT_URL,
            fetched_at=now - timedelta(minutes=2),
        ),
        _fixture_page(
            fixtures / "tipping-the-velvet.html",
            _VELVET_URL,
            fetched_at=now - timedelta(hours=5),
        ),
    )

    seed_customer_id: UUID | None = None
    worker: _FixtureWorker | None = None
    try:
        with session_scope(session_factory) as session:
            spec = registry.active_spec("books_to_scrape")
            customer = CatalogService.create_customer(
                session,
                CustomerCreate(
                    name="Northline Goods",
                    slug=_SEED_SLUG,
                    webshop_url="https://shop.example.com",
                    default_currency="GBP",
                    timezone="Europe/Copenhagen",
                ),
            )
            seed_customer_id = customer.id
            competitor = CatalogService.create_competitor(
                session,
                customer.id,
                CompetitorCreate(
                    name="Books to Scrape",
                    base_url="https://books.toscrape.com",
                    adapter_key=spec.key,
                    fetch_mode=FetchMode.HTTP,
                    expected_currency="GBP",
                    schedule_interval_seconds=3_600,
                    min_request_interval_ms=1_000,
                ),
            )
            competitor.active_scraper_revision = spec.revision

            light = CatalogService.create_product(
                session,
                customer.id,
                ProductCreate(
                    name="A Light in the Attic",
                    sku="BK-1000",
                    customer_product_url=(
                        "https://shop.example.com/products/a-light-in-the-attic"
                    ),
                    current_own_price=Decimal("49.00"),
                    currency="GBP",
                ),
            )
            light_target = CatalogService.create_competitor_product(
                session,
                light.id,
                CompetitorProductCreate(
                    competitor_id=competitor.id,
                    product_url=_LIGHT_URL,
                    expected_name="A Light in the Attic",
                    expected_currency="GBP",
                    minimum_valid_price=Decimal("1"),
                    maximum_valid_price=Decimal("500"),
                ),
            )

            velvet = CatalogService.create_product(
                session,
                customer.id,
                ProductCreate(
                    name="Tipping the Velvet",
                    sku="BK-0999",
                    customer_product_url="https://shop.example.com/products/tipping-the-velvet",
                    current_own_price=Decimal("55.00"),
                    currency="GBP",
                ),
            )
            velvet_target = CatalogService.create_competitor_product(
                session,
                velvet.id,
                CompetitorProductCreate(
                    competitor_id=competitor.id,
                    product_url=_VELVET_URL,
                    expected_name="Tipping the Velvet",
                    expected_currency="GBP",
                    minimum_valid_price=Decimal("1"),
                    maximum_valid_price=Decimal("500"),
                ),
            )
            CatalogService.create_product(
                session,
                customer.id,
                ProductCreate(
                    name="The Secret Garden",
                    sku="BK-NEW",
                    current_own_price=Decimal("18.50"),
                    currency="GBP",
                ),
            )
            light_target_id = light_target.id
            velvet_target_id = velvet_target.id

        worker = _FixtureWorker(
            session_factory=session_factory,
            settings=settings,
            registry=registry,
        )
        jobs = (
            (light_target_id, pages[0]),
            (light_target_id, pages[1]),
            (light_target_id, pages[2]),
            (velvet_target_id, pages[3]),
        )
        for target_id, page in jobs:
            await worker.process_target(target_id, page)

        with session_factory() as session:
            if not _seed_baseline_is_valid(session, seed_customer_id):
                raise RuntimeError("development seed did not produce the trusted baseline")
        return True
    except Exception:
        if seed_customer_id is not None:
            with session_scope(session_factory) as session:
                partial = session.get(Customer, seed_customer_id)
                if partial is not None and partial.slug == _SEED_SLUG:
                    session.delete(partial)
        raise
    finally:
        if worker is not None:
            await worker.aclose()


def _seed_products(session: Session, customer_id: UUID) -> dict[str, UUID]:
    rows = session.execute(
        select(Product.sku, Product.id).where(
            Product.customer_id == customer_id,
            Product.sku.in_(_SEED_SKUS),
        )
    )
    return {sku: product_id for sku, product_id in rows if sku is not None}


def _target_for_product(
    session: Session,
    product_id: UUID,
    product_url: str,
) -> CompetitorProduct | None:
    return session.scalar(
        select(CompetitorProduct)
        .where(
            CompetitorProduct.product_id == product_id,
            CompetitorProduct.product_url == product_url,
        )
        .limit(1)
    )


def _result_count(session: Session, target_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count(ScrapeResult.id)).where(
                ScrapeResult.competitor_product_id == target_id
            )
        )
        or 0
    )


def _history_count(session: Session, target_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count(PriceHistory.id)).where(
                PriceHistory.competitor_product_id == target_id
            )
        )
        or 0
    )


def _seed_is_complete(session: Session, customer_id: UUID) -> bool:
    products = _seed_products(session, customer_id)
    if set(products) != set(_SEED_SKUS):
        return False
    light = _target_for_product(session, products["BK-1000"], _LIGHT_URL)
    velvet = _target_for_product(session, products["BK-0999"], _VELVET_URL)
    if light is None or velvet is None:
        return False
    return (
        _result_count(session, light.id) >= 3
        and _history_count(session, light.id) >= 2
        and _result_count(session, velvet.id) >= 1
        and _history_count(session, velvet.id) >= 1
        and light.current_price is not None
        and velvet.current_price is not None
    )


def _seed_baseline_is_valid(session: Session, customer_id: UUID) -> bool:
    if not _seed_is_complete(session, customer_id):
        return False
    products = _seed_products(session, customer_id)
    light = _target_for_product(session, products["BK-1000"], _LIGHT_URL)
    velvet = _target_for_product(session, products["BK-0999"], _VELVET_URL)
    assert light is not None and velvet is not None
    failed = (
        session.scalar(
            select(func.count(ScrapeResult.id)).where(
                ScrapeResult.competitor_product_id == light.id,
                ScrapeResult.status == ResultStatus.FAILED,
            )
        )
        or 0
    )
    return (
        light.current_price == Decimal("47.99")
        and light.consecutive_failures == 1
        and velvet.current_price == Decimal("53.74")
        and failed >= 1
    )


def _fixture_page(path: Path, url: str, *, fetched_at: datetime) -> FetchedPage:
    html = path.read_text(encoding="utf-8")
    return FetchedPage(
        requested_url=url,
        final_url=url,
        html=html,
        status_code=200,
        fetched_at=fetched_at,
        duration_ms=12,
        safe_headers={"content-type": "text/html"},
        content_sha256=hashlib.sha256(html.encode()).hexdigest(),
    )


__all__ = ["seed_development_workspace"]
