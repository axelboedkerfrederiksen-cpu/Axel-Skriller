from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from price_monitor.domain.enums import Availability, FailureKind, FetchMode


def utc_now() -> datetime:
    return datetime.now(UTC)


class FieldEvidence(BaseModel):
    """Auditable evidence showing where an extracted value came from."""

    model_config = ConfigDict(frozen=True)

    source: Literal["css", "attribute", "json_ld", "meta", "derived"]
    selector: str | None = None
    attribute: str | None = None
    raw_value: str = Field(max_length=2_000)
    container_text: str | None = Field(default=None, max_length=4_000)


class ExtractedProduct(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=500)
    price: Decimal
    currency: str = Field(min_length=3, max_length=3)
    availability: Availability = Availability.UNKNOWN
    product_url: HttpUrl
    external_product_id: str | None = Field(default=None, max_length=300)
    observed_at: datetime = Field(default_factory=utc_now)
    evidence: dict[str, FieldEvidence]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class FetchedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_url: HttpUrl
    final_url: HttpUrl
    html: str
    status_code: int = Field(ge=100, le=599)
    fetched_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(ge=0)
    safe_headers: dict[str, str] = Field(default_factory=dict)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ScrapeTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    competitor_product_id: str
    url: HttpUrl
    allowed_hosts: tuple[str, ...]
    adapter_key: str
    adapter_revision: str
    fetch_mode: FetchMode
    expected_name: str | None = None
    expected_external_id: str | None = None
    expected_currency: str | None = None
    minimum_valid_price: Decimal | None = None
    maximum_valid_price: Decimal | None = None
    previous_price: Decimal | None = None
    previous_currency: str | None = None
    maximum_price_change_ratio: Decimal = Decimal("0.80")


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    severity: Literal["warning", "error"]
    failure_kind: FailureKind
    context: dict[str, Any] = Field(default_factory=dict)


class ValidationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def primary_failure_kind(self) -> FailureKind | None:
        return next(
            (issue.failure_kind for issue in self.issues if issue.severity == "error"),
            None,
        )
