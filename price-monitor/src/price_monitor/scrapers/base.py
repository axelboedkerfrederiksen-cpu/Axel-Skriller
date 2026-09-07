from __future__ import annotations

from typing import Protocol

from price_monitor.domain.enums import FailureKind
from price_monitor.domain.types import ExtractedProduct, FetchedPage
from price_monitor.scrapers.spec import SiteSpec


class ScraperError(ValueError):
    """Base error for deterministic extraction failures."""

    kind = FailureKind.EXTRACTION


class ScraperExtractionError(ScraperError):
    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        selector_attempts: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.field = field
        self.selector_attempts = selector_attempts


class ScraperAdapter(Protocol):
    """Pure adapter contract: fetched HTML in, typed product data out."""

    spec: SiteSpec

    def extract(self, page: FetchedPage) -> ExtractedProduct: ...
