from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from price_monitor.api.dashboard_schemas import (
    DashboardCompetitorSummary,
    DashboardHealth,
    DashboardOverview,
    DashboardProductComparison,
    DashboardProductDetail,
)
from price_monitor.api.dependencies import SessionDep
from price_monitor.services.dashboard import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get(
    "/customers/{customer_id}/dashboard",
    response_model=DashboardOverview,
)
def dashboard_overview(customer_id: UUID, session: SessionDep) -> DashboardOverview:
    return DashboardService.overview(session, customer_id)


@router.get(
    "/customers/{customer_id}/dashboard/products",
    response_model=list[DashboardProductComparison],
)
def dashboard_products(
    customer_id: UUID,
    session: SessionDep,
) -> list[DashboardProductComparison]:
    return DashboardService.products(session, customer_id)


@router.get(
    "/customers/{customer_id}/dashboard/products/{product_id}",
    response_model=DashboardProductDetail,
)
def dashboard_product_detail(
    customer_id: UUID,
    product_id: UUID,
    session: SessionDep,
) -> DashboardProductDetail:
    return DashboardService.product_detail(session, customer_id, product_id)


@router.get(
    "/customers/{customer_id}/dashboard/competitors",
    response_model=list[DashboardCompetitorSummary],
)
def dashboard_competitors(
    customer_id: UUID,
    session: SessionDep,
) -> list[DashboardCompetitorSummary]:
    return DashboardService.competitors(session, customer_id)


@router.get(
    "/customers/{customer_id}/dashboard/health",
    response_model=DashboardHealth,
)
def dashboard_health(customer_id: UUID, session: SessionDep) -> DashboardHealth:
    return DashboardService.health(session, customer_id)
