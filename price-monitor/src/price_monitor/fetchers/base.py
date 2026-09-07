from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import HttpUrl

from price_monitor.domain.enums import FailureKind
from price_monitor.domain.types import FetchedPage


class FetchError(RuntimeError):
    """A bounded, user-safe description of a page fetch failure."""

    def __init__(
        self,
        message: str,
        *,
        kind: FailureKind = FailureKind.TRANSPORT,
        url: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.url = url
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds: float | None = retry_after_seconds


class PageFetcher(Protocol):
    """Transport-neutral fetch contract used by scraper workers."""

    async def fetch(
        self,
        url: str | HttpUrl,
        *,
        allowed_hosts: Sequence[str],
    ) -> FetchedPage: ...
