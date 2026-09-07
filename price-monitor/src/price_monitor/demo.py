from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from price_monitor.api.schemas import (
    CompetitorCreate,
    CompetitorProductCreate,
    CustomerCreate,
    ProductCreate,
)
from price_monitor.config import Settings
from price_monitor.db import (
    PriceHistory,
    RepairAttempt,
    ScrapeResult,
    create_db_engine,
    create_schema,
    create_session_factory,
    session_scope,
)
from price_monitor.domain.enums import FetchMode, RepairStatus
from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.repair import (
    DeterministicSelectorProposalProvider,
    DevelopmentSubprocessSpecRunner,
    GuardedRepairWorkflow,
    ManualRepairProvider,
    RepairFixture,
    RepairRequest,
    TrustedRepairReviewer,
)
from price_monitor.scrapers.spec import SelectorRule, SiteSpec
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.artifacts import LocalArtifactStore
from price_monitor.services.catalog import CatalogService
from price_monitor.services.queue import ClaimedScrape, ScrapeQueue
from price_monitor.services.repair_coordinator import RepairCoordinator
from price_monitor.services.worker import ScrapeWorker


@dataclass(frozen=True, slots=True)
class DemoReport:
    initial_price: str
    changed_price: str
    previous_price: str
    price_change_kind: str
    history_rows_before_failure: int
    failure_status: str
    repair_created: bool
    bad_candidate_rejected: bool
    good_candidate_validated: bool
    deployed_revision: str
    repaired_scrape_status: str
    history_rows_after_repair: int
    rollback_revision_available: str
    network_used: bool = False


class _FixtureWorker(ScrapeWorker):
    def __init__(self, *args: object, pages: list[FetchedPage], **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._pages = pages

    async def _fetch(self, claimed: ClaimedScrape) -> FetchedPage:
        del claimed
        if not self._pages:
            raise RuntimeError("demo fixture queue is empty")
        return self._pages.pop(0)


async def run_demo(work_root: Path, *, fixture_root: Path | None = None) -> DemoReport:
    """Run the entire beta loop deterministically without public-network dependency."""

    fixtures = fixture_root or Path(__file__).resolve().parent / "demo_fixtures"
    books = fixtures / "books_to_scrape"
    work_root.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=work_root / "artifacts",
        adapter_runtime_root=work_root / "adapters",
        repair_failure_threshold=1,
        repair_minimum_distinct_targets=1,
        repair_cooldown_seconds=0,
        respect_robots_txt=False,
    )
    engine = create_db_engine(settings.database_url)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    registry = AdapterRegistry(settings.adapter_runtime_root)
    baseline = registry.active_spec("books_to_scrape")

    with session_scope(session_factory) as session:
        customer = CatalogService.create_customer(
            session,
            CustomerCreate(
                name="Demo Webshop",
                slug="demo-webshop",
                webshop_url="https://shop.example.com",
                default_currency="GBP",
            ),
        )
        competitor = CatalogService.create_competitor(
            session,
            customer.id,
            CompetitorCreate(
                name="Books to Scrape",
                base_url="https://books.toscrape.com",
                adapter_key=baseline.key,
                fetch_mode=FetchMode.HTTP,
                expected_currency="GBP",
                min_request_interval_ms=1_000,
            ),
        )
        competitor.active_scraper_revision = baseline.revision
        product = CatalogService.create_product(
            session,
            customer.id,
            ProductCreate(name="A Light in the Attic", sku="demo-book-1"),
        )
        target = CatalogService.create_competitor_product(
            session,
            product.id,
            CompetitorProductCreate(
                competitor_id=competitor.id,
                product_url=(
                    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
                ),
                expected_name="A Light in the Attic",
                expected_currency="GBP",
                minimum_valid_price=Decimal("1"),
                maximum_valid_price=Decimal("500"),
            ),
        )
        target_id = target.id
        competitor_id = competitor.id

    pages = [
        _page(books / "a-light-in-the-attic.html"),
        _page(books / "a-light-price-change.html"),
        _page(books / "a-light-broken-selector.html"),
    ]
    worker = _FixtureWorker(
        session_factory=session_factory,
        settings=settings,
        registry=registry,
        artifact_store=LocalArtifactStore(settings.artifact_root),
        pages=pages,
    )
    queue = ScrapeQueue(lease_seconds=settings.worker_lease_seconds)

    for _ in range(3):
        with session_scope(session_factory) as session:
            queue.enqueue_target(session, target_id)
        processed = await worker.process_one()
        if not processed:
            raise RuntimeError("demo worker failed to claim its queued scrape")

    with session_scope(session_factory) as session:
        results = list(
            session.scalars(
                select(ScrapeResult)
                .where(ScrapeResult.competitor_product_id == target_id)
                .order_by(ScrapeResult.queued_at, ScrapeResult.id)
            )
        )
        history = list(
            session.scalars(
                select(PriceHistory)
                .where(PriceHistory.competitor_product_id == target_id)
                .order_by(PriceHistory.observed_at, PriceHistory.id)
            )
        )
        repair = session.scalar(
            select(RepairAttempt).where(RepairAttempt.competitor_id == competitor_id)
        )
        if len(results) != 3 or len(history) != 2 or repair is None:
            raise RuntimeError("demo failed to produce history and a repair task")
        repair_id = repair.id

    review_fixtures = _repair_fixtures(books, baseline)
    runner = DevelopmentSubprocessSpecRunner(environment="test")
    bad_spec = _bad_candidate(baseline)
    bad_workflow = GuardedRepairWorkflow(
        provider=ManualRepairProvider(bad_spec),
        reviewer=TrustedRepairReviewer(runner),
        versions=registry.version_store,
    )
    repair_request = RepairRequest(
        baseline=baseline,
        new_html=(books / "a-light-broken-selector.html").read_text(encoding="utf-8"),
        failed_fields=frozenset({"price"}),
    )
    bad_evaluation = bad_workflow.evaluate(repair_request, fixtures=review_fixtures)

    coordinator = RepairCoordinator(
        session_factory=session_factory,
        settings=settings,
        registry=registry,
        artifacts=worker.artifacts,
        provider=DeterministicSelectorProposalProvider(),
        runner=runner,
    )
    evaluated = coordinator.evaluate_one()
    if evaluated is None or evaluated.status != RepairStatus.VALIDATED:
        raise RuntimeError("deterministic repair candidate did not pass its review gate")
    deployed = coordinator.deploy(repair_id)
    if deployed.status != RepairStatus.DEPLOYED:
        raise RuntimeError("validated repair was not deployed")
    active = registry.version_store.get_active(baseline.key)

    repaired_page = _page(books / "a-light-broken-selector.html")
    worker._pages.append(repaired_page)
    with session_scope(session_factory) as session:
        queue.enqueue_target(session, target_id)
    await worker.process_one()
    await worker.aclose()

    with session_scope(session_factory) as session:
        final_results = list(
            session.scalars(
                select(ScrapeResult)
                .where(ScrapeResult.competitor_product_id == target_id)
                .order_by(ScrapeResult.queued_at, ScrapeResult.id)
            )
        )
        final_history_count = (
            session.scalar(
                select(func.count(PriceHistory.id)).where(
                    PriceHistory.competitor_product_id == target_id
                )
            )
            or 0
        )

    return DemoReport(
        initial_price=str(history[0].price),
        changed_price=str(history[1].price),
        previous_price=str(history[1].previous_price),
        price_change_kind=history[1].change_kind.value,
        history_rows_before_failure=len(history),
        failure_status=results[2].status.value,
        repair_created=True,
        bad_candidate_rejected=not bool(bad_evaluation.review and bad_evaluation.review.accepted),
        good_candidate_validated=evaluated.status == RepairStatus.VALIDATED,
        deployed_revision=active.spec.revision,
        repaired_scrape_status=final_results[-1].status.value,
        history_rows_after_repair=final_history_count,
        rollback_revision_available=baseline.revision,
    )


def _page(path: Path, *, name: str = "a-light-in-the-attic_1000") -> FetchedPage:
    html = path.read_text(encoding="utf-8")
    url = f"https://books.toscrape.com/catalogue/{name}/index.html"
    return FetchedPage(
        requested_url=url,
        final_url=url,
        html=html,
        status_code=200,
        duration_ms=12,
        safe_headers={"content-type": "text/html"},
        content_sha256=hashlib.sha256(html.encode()).hexdigest(),
    )


def _review_target(
    *, name: str, revision: str, url_slug: str, previous_price: Decimal | None = None
) -> ScrapeTarget:
    return ScrapeTarget(
        competitor_product_id=f"fixture-{url_slug}",
        url=f"https://books.toscrape.com/catalogue/{url_slug}/index.html",
        allowed_hosts=("books.toscrape.com",),
        adapter_key="books_to_scrape",
        adapter_revision=revision,
        fetch_mode=FetchMode.HTTP,
        expected_name=name,
        expected_currency="GBP",
        minimum_valid_price=Decimal("1"),
        maximum_valid_price=Decimal("500"),
        previous_price=previous_price,
        previous_currency="GBP" if previous_price is not None else None,
    )


def _repair_fixtures(books: Path, baseline: SiteSpec) -> tuple[RepairFixture, ...]:
    return (
        RepairFixture(
            name="known-good-v1",
            cohort="old",
            page=_page(books / "a-light-in-the-attic.html"),
            target=_review_target(
                name="A Light in the Attic",
                revision=baseline.revision,
                url_slug="a-light-in-the-attic_1000",
            ),
            expected_name="A Light in the Attic",
            expected_price=Decimal("51.77"),
            expected_currency="GBP",
        ),
        RepairFixture(
            name="new-failing-dom",
            cohort="new",
            page=_page(books / "a-light-broken-selector.html"),
            target=_review_target(
                name="A Light in the Attic",
                revision=baseline.revision,
                url_slug="a-light-in-the-attic_1000",
            ),
            expected_name="A Light in the Attic",
            expected_price=Decimal("47.99"),
            expected_currency="GBP",
        ),
        RepairFixture(
            name="sibling-holdout",
            cohort="holdout",
            page=_page(
                books / "tipping-the-velvet.html",
                name="tipping-the-velvet_999",
            ),
            target=_review_target(
                name="Tipping the Velvet",
                revision=baseline.revision,
                url_slug="tipping-the-velvet_999",
            ),
            expected_name="Tipping the Velvet",
            expected_price=Decimal("53.74"),
            expected_currency="GBP",
        ),
    )


def _bad_candidate(baseline: SiteSpec) -> SiteSpec:
    values = baseline.model_dump(mode="python")
    values["revision"] = "bad-price-selector"
    values["price"] = (SelectorRule(selector=".availability"), *baseline.price)
    return SiteSpec.model_validate(values)
