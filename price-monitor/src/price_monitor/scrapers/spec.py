from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from price_monitor.domain.enums import FetchMode


class SelectorRule(BaseModel):
    """A bounded, declarative extraction rule safe to validate and version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selector: str = Field(min_length=1, max_length=300)
    attribute: str | None = Field(default=None, max_length=100)
    source: Literal["css", "meta"] = "css"
    pattern: str | None = Field(default=None, max_length=300)

    @field_validator("selector")
    @classmethod
    def selector_is_bounded(cls, value: str) -> str:
        if any(token in value for token in ("javascript:", "url(", "@import", "\\x00")):
            raise ValueError("unsafe selector content")
        return value

    @field_validator("pattern")
    @classmethod
    def regex_is_bounded(cls, value: str | None) -> str | None:
        if value is not None:
            re.compile(value)
        return value


class SiteSpec(BaseModel):
    """Versioned site-owned scraper configuration.

    Declarative specs are the only automatically promotable repair surface. Custom
    Python adapters can implement the same extraction contract, but require manual
    code review and deployment.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    revision: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    fetch_mode: FetchMode = FetchMode.HTTP
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=20)
    product_container: str = Field(default="body", min_length=1, max_length=300)
    name: tuple[SelectorRule, ...] = Field(min_length=1, max_length=10)
    price: tuple[SelectorRule, ...] = Field(min_length=1, max_length=10)
    currency: tuple[SelectorRule, ...] = Field(default=(), max_length=10)
    availability: tuple[SelectorRule, ...] = Field(default=(), max_length=10)
    external_product_id: tuple[SelectorRule, ...] = Field(default=(), max_length=10)
    currency_symbol_map: dict[str, str] = Field(
        default_factory=lambda: {"£": "GBP", "$": "USD", "€": "EUR"},
        max_length=20,
    )
    in_stock_terms: tuple[str, ...] = ("in stock", "available")
    out_of_stock_terms: tuple[str, ...] = ("out of stock", "unavailable", "sold out")
    preorder_terms: tuple[str, ...] = ("pre-order", "preorder")

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(host.strip().lower().rstrip(".") for host in value)
        if any(not host or ":" in host or "/" in host for host in normalized):
            raise ValueError("allowed_hosts must contain bare DNS hostnames")
        return normalized

    @field_validator("currency_symbol_map")
    @classmethod
    def normalize_currencies(cls, value: dict[str, str]) -> dict[str, str]:
        return {symbol: currency.upper() for symbol, currency in value.items()}

    @model_validator(mode="after")
    def browser_mode_is_explicit(self) -> SiteSpec:
        if self.fetch_mode not in (FetchMode.HTTP, FetchMode.BROWSER):
            raise ValueError("unsupported fetch mode")
        return self
