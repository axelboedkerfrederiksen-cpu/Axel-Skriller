from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from price_monitor.domain.enums import Availability


class PricePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    competitor_id: UUID
    competitor_product_id: UUID
    observed_at: datetime
    price: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    availability: Availability


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    own_price: Decimal | None = Field(default=None, gt=0)
    own_currency: str | None = Field(default=None, min_length=3, max_length=3)
    observations: tuple[PricePoint, ...]


class PricingInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2_000)
    confidence: Decimal = Field(ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PricingAnalyzer(Protocol):
    """Future pricing-analysis boundary; no analyzer is coupled to scraping."""

    def analyze(self, request: AnalysisRequest) -> tuple[PricingInsight, ...]: ...
