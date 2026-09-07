from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from price_monitor.domain.enums import MatchMethod


class MatchCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_name: str = Field(min_length=1, max_length=500)
    sku: str | None = Field(default=None, max_length=300)
    gtin: str | None = Field(default=None, max_length=30)
    competitor_name: str = Field(min_length=1, max_length=500)
    competitor_identifier: str | None = Field(default=None, max_length=300)
    competitor_url: HttpUrl


class MatchDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    matched: bool
    method: MatchMethod
    confidence: Decimal = Field(ge=0, le=1)
    explanation: str = Field(max_length=2_000)


class ProductMatcher(Protocol):
    """Extension point after exact SKU/GTIN matching cannot decide."""

    def match(self, candidate: MatchCandidate) -> MatchDecision: ...
