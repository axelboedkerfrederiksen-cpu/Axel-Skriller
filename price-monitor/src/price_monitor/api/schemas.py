from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from price_monitor.domain.enums import FetchMode, MatchMethod


class OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AdapterRead(BaseModel):
    key: str
    display_name: str
    allowed_hosts: tuple[str, ...]
    fetch_mode: FetchMode


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    webshop_url: HttpUrl
    default_currency: str = Field(default="USD", min_length=3, max_length=3)
    timezone: str = Field(default="UTC", max_length=100)

    @field_validator("default_currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    webshop_url: HttpUrl | None = None
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    @field_validator("default_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CustomerRead(OrmSchema):
    id: UUID
    name: str
    slug: str
    webshop_url: str
    default_currency: str
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_url: HttpUrl
    adapter_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    fetch_mode: FetchMode = FetchMode.HTTP
    schedule_interval_seconds: int = Field(default=3_600, ge=60, le=2_592_000)
    min_request_interval_ms: int = Field(default=1_000, ge=0, le=600_000)
    timeout_seconds: int = Field(default=15, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    expected_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("expected_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CompetitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: HttpUrl | None = None
    schedule_interval_seconds: int | None = Field(default=None, ge=60, le=2_592_000)
    min_request_interval_ms: int | None = Field(default=None, ge=0, le=600_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    expected_currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None

    @field_validator("expected_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CompetitorRead(OrmSchema):
    id: UUID
    customer_id: UUID
    name: str
    base_url: str
    adapter_key: str
    fetch_mode: FetchMode
    schedule_interval_seconds: int
    min_request_interval_ms: int
    timeout_seconds: int
    max_retries: int
    expected_currency: str | None
    active_scraper_revision: str
    previous_scraper_revision: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    sku: str | None = Field(default=None, max_length=200)
    customer_product_url: HttpUrl | None = None
    current_own_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def price_has_currency(self) -> ProductCreate:
        if (self.current_own_price is None) != (self.currency is None):
            raise ValueError("current_own_price and currency must be supplied together")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    sku: str | None = Field(default=None, max_length=200)
    customer_product_url: HttpUrl | None = None
    current_own_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ProductRead(OrmSchema):
    id: UUID
    customer_id: UUID
    name: str
    sku: str | None
    customer_product_url: str | None
    current_own_price: Decimal | None
    currency: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CompetitorProductCreate(BaseModel):
    competitor_id: UUID
    product_url: HttpUrl
    external_product_id: str | None = Field(default=None, max_length=300)
    match_method: MatchMethod = MatchMethod.MANUAL
    match_confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    expected_name: str | None = Field(default=None, max_length=500)
    expected_currency: str | None = Field(default=None, min_length=3, max_length=3)
    minimum_valid_price: Decimal | None = Field(default=None, gt=0)
    maximum_valid_price: Decimal | None = Field(default=None, gt=0)
    schedule_interval_seconds: int | None = Field(default=None, ge=60, le=2_592_000)

    @field_validator("expected_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> CompetitorProductCreate:
        if (
            self.minimum_valid_price is not None
            and self.maximum_valid_price is not None
            and self.minimum_valid_price > self.maximum_valid_price
        ):
            raise ValueError("minimum_valid_price cannot exceed maximum_valid_price")
        return self


class CompetitorProductUpdate(BaseModel):
    product_url: HttpUrl | None = None
    external_product_id: str | None = Field(default=None, max_length=300)
    expected_name: str | None = Field(default=None, max_length=500)
    expected_currency: str | None = Field(default=None, min_length=3, max_length=3)
    minimum_valid_price: Decimal | None = Field(default=None, gt=0)
    maximum_valid_price: Decimal | None = Field(default=None, gt=0)
    schedule_interval_seconds: int | None = Field(default=None, ge=60, le=2_592_000)
    is_active: bool | None = None

    @field_validator("expected_currency")
    @classmethod
    def uppercase_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CompetitorProductRead(OrmSchema):
    id: UUID
    product_id: UUID
    competitor_id: UUID
    product_url: str
    external_product_id: str | None
    match_method: MatchMethod
    match_confidence: Decimal | None
    expected_name: str | None
    expected_currency: str | None
    minimum_valid_price: Decimal | None
    maximum_valid_price: Decimal | None
    schedule_interval_seconds: int | None
    next_scrape_at: datetime
    current_price: Decimal | None
    current_currency: str | None
    current_availability: str | None
    current_observed_at: datetime | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    consecutive_failures: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScrapeQueued(BaseModel):
    scrape_result_id: UUID
    status: str


class ScrapeResultRead(OrmSchema):
    id: UUID
    run_key: str
    competitor_product_id: UUID
    status: str
    queued_at: datetime
    started_at: datetime | None
    observed_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    scraper_revision: str
    fetch_mode: str
    http_status: int | None
    observed_name: str | None
    price: Decimal | None
    currency: str | None
    availability: str | None
    raw_price_text: str | None
    previous_price: Decimal | None
    previous_currency: str | None
    is_price_change: bool | None
    failure_kind: str | None
    failure_code: str | None
    failure_message: str | None
    validation_errors: list[dict[str, Any]]
    extraction_evidence: dict[str, Any]
    html_artifact_uri: str | None
    html_sha256: str | None


class MonitoringStatusRead(BaseModel):
    """Small, non-diagnostic monitoring view intended for the operator UI."""

    target_id: UUID
    latest_job_status: str | None
    latest_job_queued_at: datetime | None
    latest_job_started_at: datetime | None
    latest_job_finished_at: datetime | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    current_observed_at: datetime | None
    consecutive_failures: int


class PriceHistoryRead(OrmSchema):
    id: int
    competitor_product_id: UUID
    scrape_result_id: UUID
    observed_at: datetime
    price: Decimal
    currency: str
    availability: str
    previous_price: Decimal | None
    previous_currency: str | None
    change_amount: Decimal | None
    change_percent: Decimal | None
    change_kind: str


class OfferRead(BaseModel):
    competitor_id: UUID
    competitor_name: str
    competitor_product_id: UUID
    product_url: str
    price: Decimal | None
    currency: str | None
    availability: str | None
    observed_at: datetime | None


class ScraperHealthRead(OrmSchema):
    competitor_id: UUID
    status: str
    consecutive_repairable_failures: int
    recent_failure_count: int
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure_kind: str | None
    last_failure_message: str | None
    last_scrape_result_id: UUID | None
    updated_at: datetime


class CompetitorHealthSummaryRead(BaseModel):
    """Safe scraper health fields for routine operator-facing screens."""

    competitor_id: UUID
    status: str
    consecutive_repairable_failures: int
    recent_failure_count: int
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure_kind: str | None
    updated_at: datetime


class RepairAttemptRead(OrmSchema):
    id: UUID
    competitor_id: UUID
    trigger_scrape_result_id: UUID | None
    status: str
    failure_signature: str
    diagnostic_artifact_uri: str | None
    baseline_revision: str
    candidate_revision: str | None
    patch_uri: str | None
    patch_sha256: str | None
    changed_files: list[str]
    test_report: dict[str, Any]
    validation_report: dict[str, Any]
    reviewer_decision: str | None
    rejection_reason: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
