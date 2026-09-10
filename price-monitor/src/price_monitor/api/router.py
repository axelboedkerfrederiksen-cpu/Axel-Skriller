from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from price_monitor.api.alerts import router as alert_router
from price_monitor.api.dependencies import AdapterRegistryDep, SessionDep
from price_monitor.api.schemas import (
    AdapterRead,
    CompetitorCreate,
    CompetitorHealthSummaryRead,
    CompetitorProductCreate,
    CompetitorProductRead,
    CompetitorProductUpdate,
    CompetitorRead,
    CompetitorUpdate,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    MonitoringStatusRead,
    OfferRead,
    PriceHistoryRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    RepairAttemptRead,
    ScrapeQueued,
    ScrapeResultRead,
    ScraperHealthRead,
)
from price_monitor.db.models import (
    CompetitorProduct,
    PriceHistory,
    RepairAttempt,
    ScrapeResult,
    ScraperHealth,
)
from price_monitor.domain.enums import RepairStatus
from price_monitor.services.catalog import CatalogService
from price_monitor.services.errors import ConflictError, InvalidRequestError, NotFoundError
from price_monitor.services.queue import ScrapeQueue

router = APIRouter()
router.include_router(alert_router)

Limit500 = Annotated[int, Query(ge=1, le=500)]
Limit1000 = Annotated[int, Query(ge=1, le=1_000)]
FromTime = Annotated[datetime | None, Query(alias="from")]
ToTime = Annotated[datetime | None, Query(alias="to")]
RepairStatusQuery = Annotated[RepairStatus | None, Query(alias="status")]
_ADAPTER_DISPLAY_NAMES = {"books_to_scrape": "Books to Scrape"}


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("resource conflicts with a concurrent operation") from exc


@router.get("/adapters", response_model=list[AdapterRead])
def list_adapters(registry: AdapterRegistryDep) -> list[AdapterRead]:
    return [
        AdapterRead(
            key=spec.key,
            display_name=_ADAPTER_DISPLAY_NAMES.get(spec.key, spec.key.replace("_", " ").title()),
            allowed_hosts=spec.allowed_hosts,
            fetch_mode=spec.fetch_mode,
        )
        for spec in (registry.active_spec(key) for key in sorted(registry.keys))
    ]


@router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    request: CustomerCreate,
    session: SessionDep,
) -> CustomerRead:
    customer = CatalogService.create_customer(session, request)
    _commit(session)
    return CustomerRead.model_validate(customer)


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(session: SessionDep) -> list[CustomerRead]:
    return [CustomerRead.model_validate(item) for item in CatalogService.list_customers(session)]


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: UUID, session: SessionDep) -> CustomerRead:
    return CustomerRead.model_validate(CatalogService.get_customer(session, customer_id))


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: UUID,
    request: CustomerUpdate,
    session: SessionDep,
) -> CustomerRead:
    customer = CatalogService.update_customer(session, customer_id, request)
    _commit(session)
    return CustomerRead.model_validate(customer)


@router.post(
    "/customers/{customer_id}/competitors",
    response_model=CompetitorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_competitor(
    customer_id: UUID,
    request: CompetitorCreate,
    session: SessionDep,
    registry: AdapterRegistryDep,
) -> CompetitorRead:
    spec = registry.active_spec(request.adapter_key)
    registry.validate_site_configuration(base_url=str(request.base_url), spec=spec)
    if request.fetch_mode != spec.fetch_mode:
        raise ConflictError("fetch mode must match the selected adapter")
    competitor = CatalogService.create_competitor(session, customer_id, request)
    competitor.active_scraper_revision = spec.revision
    session.flush()
    _commit(session)
    return CompetitorRead.model_validate(competitor)


@router.get(
    "/customers/{customer_id}/competitors",
    response_model=list[CompetitorRead],
)
def list_competitors(customer_id: UUID, session: SessionDep) -> list[CompetitorRead]:
    return [
        CompetitorRead.model_validate(item)
        for item in CatalogService.list_competitors(session, customer_id)
    ]


@router.get("/competitors/{competitor_id}", response_model=CompetitorRead)
def get_competitor(competitor_id: UUID, session: SessionDep) -> CompetitorRead:
    return CompetitorRead.model_validate(CatalogService.get_competitor(session, competitor_id))


@router.patch("/competitors/{competitor_id}", response_model=CompetitorRead)
def update_competitor(
    competitor_id: UUID,
    request: CompetitorUpdate,
    session: SessionDep,
    registry: AdapterRegistryDep,
) -> CompetitorRead:
    current = CatalogService.get_competitor(session, competitor_id)
    base_url = str(request.base_url) if request.base_url is not None else current.base_url
    registry.validate_site_configuration(
        base_url=base_url,
        spec=registry.spec_at(current.adapter_key, current.active_scraper_revision),
    )
    competitor = CatalogService.update_competitor(session, competitor_id, request)
    _commit(session)
    return CompetitorRead.model_validate(competitor)


@router.get("/competitors/{competitor_id}/health", response_model=ScraperHealthRead)
def get_competitor_health(competitor_id: UUID, session: SessionDep) -> ScraperHealthRead:
    CatalogService.get_competitor(session, competitor_id)
    health = session.get(ScraperHealth, competitor_id)
    if health is None:
        raise NotFoundError("scraper health has not been initialized")
    return ScraperHealthRead.model_validate(health)


@router.get(
    "/competitors/{competitor_id}/health-summary",
    response_model=CompetitorHealthSummaryRead,
)
def get_competitor_health_summary(
    competitor_id: UUID,
    session: SessionDep,
) -> CompetitorHealthSummaryRead:
    CatalogService.get_competitor(session, competitor_id)
    health = session.get(ScraperHealth, competitor_id)
    if health is None:
        raise NotFoundError("scraper health has not been initialized")
    return CompetitorHealthSummaryRead(
        competitor_id=health.competitor_id,
        status=health.status.value,
        consecutive_repairable_failures=health.consecutive_repairable_failures,
        recent_failure_count=health.recent_failure_count,
        last_attempt_at=health.last_attempt_at,
        last_success_at=health.last_success_at,
        last_failure_at=health.last_failure_at,
        last_failure_kind=(health.last_failure_kind.value if health.last_failure_kind else None),
        updated_at=health.updated_at,
    )


@router.post(
    "/customers/{customer_id}/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    customer_id: UUID,
    request: ProductCreate,
    session: SessionDep,
) -> ProductRead:
    product = CatalogService.create_product(session, customer_id, request)
    _commit(session)
    return ProductRead.model_validate(product)


@router.get("/customers/{customer_id}/products", response_model=list[ProductRead])
def list_products(customer_id: UUID, session: SessionDep) -> list[ProductRead]:
    return [
        ProductRead.model_validate(item)
        for item in CatalogService.list_products(session, customer_id)
    ]


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: UUID, session: SessionDep) -> ProductRead:
    return ProductRead.model_validate(CatalogService.get_product(session, product_id))


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: UUID,
    request: ProductUpdate,
    session: SessionDep,
) -> ProductRead:
    product = CatalogService.update_product(session, product_id, request)
    _commit(session)
    return ProductRead.model_validate(product)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(product_id: UUID, session: SessionDep) -> Response:
    CatalogService.delete_product(session, product_id)
    _commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/products/{product_id}/competitor-products",
    response_model=CompetitorProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_competitor_product(
    product_id: UUID,
    request: CompetitorProductCreate,
    session: SessionDep,
) -> CompetitorProductRead:
    target = CatalogService.create_competitor_product(session, product_id, request)
    _commit(session)
    return CompetitorProductRead.model_validate(target)


@router.get(
    "/products/{product_id}/competitor-products",
    response_model=list[CompetitorProductRead],
)
def list_competitor_products(product_id: UUID, session: SessionDep) -> list[CompetitorProductRead]:
    return [
        CompetitorProductRead.model_validate(item)
        for item in CatalogService.list_competitor_products(session, product_id)
    ]


@router.patch("/competitor-products/{target_id}", response_model=CompetitorProductRead)
def update_competitor_product(
    target_id: UUID,
    request: CompetitorProductUpdate,
    session: SessionDep,
) -> CompetitorProductRead:
    target = CatalogService.update_competitor_product(session, target_id, request)
    _commit(session)
    return CompetitorProductRead.model_validate(target)


@router.get(
    "/competitor-products/{target_id}/monitoring-status",
    response_model=MonitoringStatusRead,
)
def get_monitoring_status(target_id: UUID, session: SessionDep) -> MonitoringStatusRead:
    target = CatalogService.get_competitor_product(session, target_id)
    latest_job = session.scalar(
        select(ScrapeResult)
        .where(ScrapeResult.competitor_product_id == target_id)
        .order_by(ScrapeResult.queued_at.desc(), ScrapeResult.id.desc())
        .limit(1)
    )
    return MonitoringStatusRead(
        target_id=target.id,
        latest_job_status=latest_job.status.value if latest_job else None,
        latest_job_queued_at=latest_job.queued_at if latest_job else None,
        latest_job_started_at=latest_job.started_at if latest_job else None,
        latest_job_finished_at=latest_job.finished_at if latest_job else None,
        last_attempt_at=target.last_attempt_at,
        last_success_at=target.last_success_at,
        current_observed_at=target.current_observed_at,
        consecutive_failures=target.consecutive_failures,
    )


@router.post(
    "/competitor-products/{target_id}/scrapes",
    response_model=ScrapeQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_scrape(
    target_id: UUID,
    response: Response,
    session: SessionDep,
) -> ScrapeQueued:
    result = ScrapeQueue().enqueue_target(session, target_id)
    _commit(session)
    if result.status != "queued":
        response.status_code = status.HTTP_200_OK
    return ScrapeQueued(scrape_result_id=result.id, status=result.status.value)


@router.get("/scrape-results/{result_id}", response_model=ScrapeResultRead)
def get_scrape_result(result_id: UUID, session: SessionDep) -> ScrapeResultRead:
    result = session.get(ScrapeResult, result_id)
    if result is None:
        raise NotFoundError(f"ScrapeResult {result_id} was not found")
    return ScrapeResultRead.model_validate(result)


@router.get(
    "/competitor-products/{target_id}/scrape-results",
    response_model=list[ScrapeResultRead],
)
def list_scrape_results(
    target_id: UUID,
    session: SessionDep,
    limit: Limit500 = 100,
) -> list[ScrapeResultRead]:
    CatalogService.get_competitor_product(session, target_id)
    values = session.scalars(
        select(ScrapeResult)
        .where(ScrapeResult.competitor_product_id == target_id)
        .order_by(ScrapeResult.queued_at.desc(), ScrapeResult.id.desc())
        .limit(limit)
    )
    return [ScrapeResultRead.model_validate(value) for value in values]


@router.get("/products/{product_id}/price-history", response_model=list[PriceHistoryRead])
def list_price_history(
    product_id: UUID,
    session: SessionDep,
    competitor_id: UUID | None = None,
    from_time: FromTime = None,
    to_time: ToTime = None,
    limit: Limit1000 = 200,
) -> list[PriceHistoryRead]:
    CatalogService.get_product(session, product_id)
    for label, value in (("from", from_time), ("to", to_time)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise InvalidRequestError(f"{label} timestamp must include a timezone")
    if from_time is not None and to_time is not None and from_time > to_time:
        raise InvalidRequestError("from timestamp cannot be later than to timestamp")
    statement = (
        select(PriceHistory)
        .join(
            CompetitorProduct,
            PriceHistory.competitor_product_id == CompetitorProduct.id,
        )
        .where(CompetitorProduct.product_id == product_id)
    )
    if competitor_id is not None:
        statement = statement.where(CompetitorProduct.competitor_id == competitor_id)
    if from_time is not None:
        statement = statement.where(PriceHistory.observed_at >= from_time)
    if to_time is not None:
        statement = statement.where(PriceHistory.observed_at <= to_time)
    values = session.scalars(
        statement.order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc()).limit(limit)
    )
    return [PriceHistoryRead.model_validate(value) for value in values]


@router.get("/products/{product_id}/offers", response_model=list[OfferRead])
def list_offers(product_id: UUID, session: SessionDep) -> list[OfferRead]:
    CatalogService.get_product(session, product_id)
    targets = session.scalars(
        select(CompetitorProduct)
        .options(joinedload(CompetitorProduct.competitor))
        .where(
            CompetitorProduct.product_id == product_id,
            CompetitorProduct.is_active.is_(True),
        )
        .order_by(CompetitorProduct.current_price.asc().nulls_last())
    )
    return [
        OfferRead(
            competitor_id=target.competitor_id,
            competitor_name=target.competitor.name,
            competitor_product_id=target.id,
            product_url=target.product_url,
            price=target.current_price,
            currency=target.current_currency,
            availability=(
                target.current_availability.value if target.current_availability else None
            ),
            observed_at=target.current_observed_at,
        )
        for target in targets
    ]


@router.get("/repair-attempts", response_model=list[RepairAttemptRead])
def list_repair_attempts(
    session: SessionDep,
    repair_status: RepairStatusQuery = None,
    limit: Limit500 = 100,
) -> list[RepairAttemptRead]:
    statement = select(RepairAttempt)
    if repair_status is not None:
        statement = statement.where(RepairAttempt.status == repair_status)
    values = session.scalars(
        statement.order_by(RepairAttempt.queued_at.desc(), RepairAttempt.id.desc()).limit(limit)
    )
    return [RepairAttemptRead.model_validate(value) for value in values]


@router.get("/repair-attempts/{repair_id}", response_model=RepairAttemptRead)
def get_repair_attempt(repair_id: UUID, session: SessionDep) -> RepairAttemptRead:
    repair = session.get(RepairAttempt, repair_id)
    if repair is None:
        raise NotFoundError(f"RepairAttempt {repair_id} was not found")
    return RepairAttemptRead.model_validate(repair)
