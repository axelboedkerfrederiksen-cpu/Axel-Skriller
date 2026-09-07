from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MonitorStatus = Literal["healthy", "stale", "failed"]
PriceEventType = Literal[
    "price_drop",
    "price_increase",
    "out_of_stock",
    "back_in_stock",
    "became_cheapest",
]


class DashboardSchema(BaseModel):
    """Camel-cased read models consumed by the Pricegrid dashboard."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DashboardProduct(DashboardSchema):
    id: UUID
    name: str
    sku: str
    customer_price: float | None
    currency: str
    image_url: str | None = None
    in_stock: bool | None
    last_checked: datetime


class DashboardCompetitorOffer(DashboardSchema):
    id: UUID
    product_id: UUID
    competitor_id: UUID
    competitor_name: str
    price: float | None
    currency: str
    in_stock: bool | None
    product_url: str
    last_checked: datetime
    status: MonitorStatus


class DashboardPriceHistoryPoint(DashboardSchema):
    timestamp: datetime
    price: float
    source_type: Literal["customer", "competitor"]
    competitor_id: UUID | None = None
    competitor_name: str | None = None


class DashboardPriceChangeEvent(DashboardSchema):
    id: str
    product_id: UUID
    product_name: str
    competitor_id: UUID | None = None
    competitor_name: str | None = None
    currency: str
    old_price: float | None = None
    new_price: float | None = None
    percentage_change: float | None = None
    timestamp: datetime
    event_type: PriceEventType


class DashboardProductComparison(DashboardSchema):
    product: DashboardProduct
    competitor_offers: list[DashboardCompetitorOffer]
    cheapest_competitor: DashboardCompetitorOffer | None
    cheapest_price: float | None
    customer_price: float | None
    difference_amount: float | None
    difference_percentage: float | None
    customer_rank: int | None
    is_customer_cheapest: bool | None
    has_recent_competitor_drop: bool
    has_recent_competitor_increase: bool
    status: MonitorStatus


class DashboardFreshness(DashboardSchema):
    status: MonitorStatus
    last_successful_update: datetime | None
    healthy_percentage: int
    checked_last_hour: int


class DashboardOverview(DashboardSchema):
    total_products: int
    monitored_offers: int
    price_changes_24h: int = Field(alias="priceChanges24h")
    overpriced_products: int
    cheapest_products: int
    stale_or_failed: int
    recent_events: list[DashboardPriceChangeEvent]
    largest_gaps: list[DashboardProductComparison]
    freshness: DashboardFreshness


class DashboardProductDetail(DashboardSchema):
    comparison: DashboardProductComparison
    history: list[DashboardPriceHistoryPoint]
    events: list[DashboardPriceChangeEvent]


class DashboardCompetitorSummary(DashboardSchema):
    id: UUID
    name: str
    monitored_products: int
    average_difference_percentage: float | None
    cheapest_products: int
    last_successful_scrape: datetime | None
    status: MonitorStatus
    success_rate: int


class DashboardSiteMonitorStatus(DashboardSchema):
    id: UUID
    name: str
    healthy_monitors: int
    stale_monitors: int
    failed_checks: int
    last_successful_update: datetime | None
    status: MonitorStatus


class DashboardHealth(DashboardSchema):
    healthy_monitors: int
    stale_monitors: int
    failed_checks: int
    total_monitors: int
    last_successful_update: datetime | None
    sites: list[DashboardSiteMonitorStatus]
