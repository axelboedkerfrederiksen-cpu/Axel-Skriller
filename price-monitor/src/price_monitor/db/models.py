from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from price_monitor.db.base import Base
from price_monitor.db.types import UTCDateTime
from price_monitor.domain.enums import (
    Availability,
    ChangeKind,
    FailureKind,
    FetchMode,
    HealthStatus,
    MatchMethod,
    RepairStatus,
    ResultStatus,
)
from price_monitor.domain.types import utc_now

MONEY = Numeric(18, 4, asdecimal=True)
PERCENT = Numeric(18, 6, asdecimal=True)
CONFIDENCE = Numeric(5, 4, asdecimal=True)


def _enum_type(enum_class: type[StrEnum], name: str) -> SAEnum:
    """Store enum values (rather than Python member names) portably."""

    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_customers_slug"),
        CheckConstraint(
            "length(default_currency) = 3 AND default_currency = upper(default_currency)",
            name="default_currency_iso_code",
        ),
        CheckConstraint("length(timezone) > 0", name="timezone_not_empty"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    webshop_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, default="UTC", server_default="UTC"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    competitors: Mapped[list[Competitor]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    products: Mapped[list[Product]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Competitor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competitors"
    __table_args__ = (
        UniqueConstraint("customer_id", "name", name="uq_competitors_customer_name"),
        UniqueConstraint("customer_id", "base_url", name="uq_competitors_customer_base_url"),
        CheckConstraint("schedule_interval_seconds > 0", name="schedule_interval_positive"),
        CheckConstraint("min_request_interval_ms >= 0", name="request_interval_nonnegative"),
        CheckConstraint("timeout_seconds > 0", name="timeout_positive"),
        CheckConstraint("max_retries >= 0", name="max_retries_nonnegative"),
        CheckConstraint(
            "expected_currency IS NULL OR "
            "(length(expected_currency) = 3 AND expected_currency = upper(expected_currency))",
            name="expected_currency_iso_code",
        ),
        Index("ix_competitors_customer_id", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(200), nullable=False)
    fetch_mode: Mapped[FetchMode] = mapped_column(
        _enum_type(FetchMode, "fetch_mode"),
        nullable=False,
        default=FetchMode.HTTP,
        server_default=FetchMode.HTTP.value,
    )
    schedule_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3_600, server_default=text("3600")
    )
    min_request_interval_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1_000, server_default=text("1000")
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, server_default=text("15")
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("2")
    )
    expected_currency: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    active_scraper_revision: Mapped[str] = mapped_column(
        String(100), nullable=False, default="initial", server_default="initial"
    )
    previous_scraper_revision: Mapped[str | None] = mapped_column(String(100))

    customer: Mapped[Customer] = relationship(back_populates="competitors")
    competitor_products: Mapped[list[CompetitorProduct]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health: Mapped[ScraperHealth | None] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    repair_attempts: Mapped[list[RepairAttempt]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "current_own_price IS NULL OR current_own_price >= 0",
            name="own_price_nonnegative",
        ),
        CheckConstraint(
            "currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))",
            name="currency_iso_code",
        ),
        Index("ix_products_customer_id", "customer_id"),
        Index(
            "uq_products_customer_sku",
            "customer_id",
            "sku",
            unique=True,
            sqlite_where=text("sku IS NOT NULL"),
            postgresql_where=text("sku IS NOT NULL"),
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(200))
    customer_product_url: Mapped[str | None] = mapped_column(Text)
    current_own_price: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    customer: Mapped[Customer] = relationship(back_populates="products")
    competitor_products: Mapped[list[CompetitorProduct]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CompetitorProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competitor_products"
    __table_args__ = (
        UniqueConstraint("competitor_id", "product_url", name="uq_competitor_products_site_url"),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="match_confidence_range",
        ),
        CheckConstraint(
            "minimum_valid_price IS NULL OR minimum_valid_price >= 0",
            name="minimum_price_nonnegative",
        ),
        CheckConstraint(
            "maximum_valid_price IS NULL OR maximum_valid_price >= 0",
            name="maximum_price_nonnegative",
        ),
        CheckConstraint(
            "minimum_valid_price IS NULL OR maximum_valid_price IS NULL "
            "OR minimum_valid_price <= maximum_valid_price",
            name="valid_price_bounds_ordered",
        ),
        CheckConstraint(
            "schedule_interval_seconds IS NULL OR schedule_interval_seconds > 0",
            name="schedule_interval_positive",
        ),
        CheckConstraint(
            "current_price IS NULL OR current_price >= 0",
            name="current_price_nonnegative",
        ),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures_nonnegative"),
        CheckConstraint(
            "expected_currency IS NULL OR "
            "(length(expected_currency) = 3 AND expected_currency = upper(expected_currency))",
            name="expected_currency_iso_code",
        ),
        CheckConstraint(
            "current_currency IS NULL OR "
            "(length(current_currency) = 3 AND current_currency = upper(current_currency))",
            name="current_currency_iso_code",
        ),
        Index("ix_competitor_products_product_id", "product_id"),
        Index("ix_competitor_products_competitor_id", "competitor_id"),
        Index("ix_competitor_products_due", "is_active", "next_scrape_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False
    )
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_product_id: Mapped[str | None] = mapped_column(String(300))
    match_method: Mapped[MatchMethod] = mapped_column(
        _enum_type(MatchMethod, "match_method"),
        nullable=False,
        default=MatchMethod.MANUAL,
        server_default=MatchMethod.MANUAL.value,
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    expected_name: Mapped[str | None] = mapped_column(String(500))
    expected_currency: Mapped[str | None] = mapped_column(String(3))
    minimum_valid_price: Mapped[Decimal | None] = mapped_column(MONEY)
    maximum_valid_price: Mapped[Decimal | None] = mapped_column(MONEY)
    schedule_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_scrape_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP")
    )
    current_price: Mapped[Decimal | None] = mapped_column(MONEY)
    current_currency: Mapped[str | None] = mapped_column(String(3))
    current_availability: Mapped[Availability | None] = mapped_column(
        _enum_type(Availability, "availability")
    )
    current_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    product: Mapped[Product] = relationship(back_populates="competitor_products")
    competitor: Mapped[Competitor] = relationship(back_populates="competitor_products")
    scrape_results: Mapped[list[ScrapeResult]] = relationship(
        back_populates="competitor_product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    price_history: Mapped[list[PriceHistory]] = relationship(
        back_populates="competitor_product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ScrapeResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scrape_results"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_scrape_results_run_key"),
        UniqueConstraint("lease_token", name="uq_scrape_results_lease_token"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_nonnegative"),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="http_status_range",
        ),
        CheckConstraint("price IS NULL OR price >= 0", name="price_nonnegative"),
        CheckConstraint(
            "previous_price IS NULL OR previous_price >= 0",
            name="previous_price_nonnegative",
        ),
        CheckConstraint(
            "currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))",
            name="currency_iso_code",
        ),
        CheckConstraint(
            "previous_currency IS NULL OR "
            "(length(previous_currency) = 3 AND previous_currency = upper(previous_currency))",
            name="previous_currency_iso_code",
        ),
        CheckConstraint(
            "html_sha256 IS NULL OR length(html_sha256) = 64",
            name="html_sha256_length",
        ),
        Index("ix_scrape_results_target_queued", "competitor_product_id", "queued_at"),
        Index("ix_scrape_results_status_queued", "status", "queued_at"),
        Index(
            "uq_scrape_results_one_active_per_target",
            "competitor_product_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    run_key: Mapped[str] = mapped_column(String(200), nullable=False)
    competitor_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("competitor_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ResultStatus] = mapped_column(
        _enum_type(ResultStatus, "result_status"),
        nullable=False,
        default=ResultStatus.QUEUED,
        server_default=ResultStatus.QUEUED.value,
    )
    queued_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    scraper_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    fetch_mode: Mapped[FetchMode] = mapped_column(
        _enum_type(FetchMode, "fetch_mode"), nullable=False
    )
    http_status: Mapped[int | None] = mapped_column(Integer)
    observed_name: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))
    availability: Mapped[Availability | None] = mapped_column(
        _enum_type(Availability, "availability")
    )
    raw_price_text: Mapped[str | None] = mapped_column(String(500))
    previous_price: Mapped[Decimal | None] = mapped_column(MONEY)
    previous_currency: Mapped[str | None] = mapped_column(String(3))
    is_price_change: Mapped[bool | None] = mapped_column(Boolean)
    failure_kind: Mapped[FailureKind | None] = mapped_column(
        _enum_type(FailureKind, "failure_kind")
    )
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    extraction_evidence: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    html_artifact_uri: Mapped[str | None] = mapped_column(Text)
    html_sha256: Mapped[str | None] = mapped_column(String(64))
    screenshot_uri: Mapped[str | None] = mapped_column(Text)

    competitor_product: Mapped[CompetitorProduct] = relationship(back_populates="scrape_results")
    price_history: Mapped[PriceHistory | None] = relationship(
        back_populates="scrape_result", uselist=False
    )
    health_records: Mapped[list[ScraperHealth]] = relationship(
        back_populates="last_scrape_result",
        foreign_keys="ScraperHealth.last_scrape_result_id",
    )
    triggered_repairs: Mapped[list[RepairAttempt]] = relationship(
        back_populates="trigger_scrape_result",
        foreign_keys="RepairAttempt.trigger_scrape_result_id",
    )


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("scrape_result_id", name="uq_price_history_scrape_result"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint(
            "previous_price IS NULL OR previous_price >= 0",
            name="previous_price_nonnegative",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="currency_iso_code"
        ),
        CheckConstraint(
            "previous_currency IS NULL OR "
            "(length(previous_currency) = 3 AND previous_currency = upper(previous_currency))",
            name="previous_currency_iso_code",
        ),
        Index(
            "ix_price_history_target_observed",
            "competitor_product_id",
            "observed_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    competitor_product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("competitor_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    scrape_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scrape_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    availability: Mapped[Availability] = mapped_column(
        _enum_type(Availability, "availability"),
        nullable=False,
        default=Availability.UNKNOWN,
        server_default=Availability.UNKNOWN.value,
    )
    previous_price: Mapped[Decimal | None] = mapped_column(MONEY)
    previous_currency: Mapped[str | None] = mapped_column(String(3))
    change_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    change_percent: Mapped[Decimal | None] = mapped_column(PERCENT)
    change_kind: Mapped[ChangeKind] = mapped_column(
        _enum_type(ChangeKind, "change_kind"), nullable=False
    )

    competitor_product: Mapped[CompetitorProduct] = relationship(back_populates="price_history")
    scrape_result: Mapped[ScrapeResult] = relationship(back_populates="price_history")


class ScraperHealth(Base):
    __tablename__ = "scraper_health"
    __table_args__ = (
        CheckConstraint(
            "consecutive_repairable_failures >= 0",
            name="repairable_failures_nonnegative",
        ),
        CheckConstraint("recent_failure_count >= 0", name="recent_failures_nonnegative"),
        Index("ix_scraper_health_status", "status"),
        Index("ix_scraper_health_last_scrape_result_id", "last_scrape_result_id"),
    )

    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("competitors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[HealthStatus] = mapped_column(
        _enum_type(HealthStatus, "health_status"),
        nullable=False,
        default=HealthStatus.HEALTHY,
        server_default=HealthStatus.HEALTHY.value,
    )
    consecutive_repairable_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    recent_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_failure_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_failure_kind: Mapped[FailureKind | None] = mapped_column(
        _enum_type(FailureKind, "failure_kind")
    )
    last_failure_message: Mapped[str | None] = mapped_column(Text)
    last_scrape_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scrape_results.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    competitor: Mapped[Competitor] = relationship(back_populates="health")
    last_scrape_result: Mapped[ScrapeResult | None] = relationship(
        back_populates="health_records", foreign_keys=[last_scrape_result_id]
    )


class RepairAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (
        CheckConstraint(
            "patch_sha256 IS NULL OR length(patch_sha256) = 64",
            name="patch_sha256_length",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(status IN ('diagnosing', 'candidate_ready', 'testing') "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status NOT IN ('diagnosing', 'candidate_ready', 'testing') "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="lease_matches_processing_status",
        ),
        UniqueConstraint("lease_token", name="uq_repair_attempts_lease_token"),
        Index("ix_repair_attempts_status_queued", "status", "queued_at"),
        Index("ix_repair_attempts_trigger_scrape_result_id", "trigger_scrape_result_id"),
        Index(
            "ix_repair_attempts_claimable",
            "status",
            "lease_expires_at",
            "queued_at",
        ),
        Index(
            "uq_repair_attempts_one_open_per_competitor",
            "competitor_id",
            unique=True,
            sqlite_where=text(
                "status IN ('queued', 'diagnosing', 'candidate_ready', 'testing', 'validated')"
            ),
            postgresql_where=text(
                "status IN ('queued', 'diagnosing', 'candidate_ready', 'testing', 'validated')"
            ),
        ),
    )

    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False
    )
    trigger_scrape_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scrape_results.id", ondelete="SET NULL")
    )
    status: Mapped[RepairStatus] = mapped_column(
        _enum_type(RepairStatus, "repair_status"),
        nullable=False,
        default=RepairStatus.QUEUED,
        server_default=RepairStatus.QUEUED.value,
    )
    failure_signature: Mapped[str] = mapped_column(String(500), nullable=False)
    diagnostic_artifact_uri: Mapped[str | None] = mapped_column(Text)
    baseline_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_revision: Mapped[str | None] = mapped_column(String(100))
    patch_uri: Mapped[str | None] = mapped_column(Text)
    patch_sha256: Mapped[str | None] = mapped_column(String(64))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    changed_files: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    test_report: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    validation_report: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    reviewer_decision: Mapped[str | None] = mapped_column(String(100))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    candidate_ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    testing_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deployed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    rolled_back_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    competitor: Mapped[Competitor] = relationship(back_populates="repair_attempts")
    trigger_scrape_result: Mapped[ScrapeResult | None] = relationship(
        back_populates="triggered_repairs", foreign_keys=[trigger_scrape_result_id]
    )


ALL_MODELS = (
    Customer,
    Competitor,
    Product,
    CompetitorProduct,
    ScrapeResult,
    PriceHistory,
    ScraperHealth,
    RepairAttempt,
)
