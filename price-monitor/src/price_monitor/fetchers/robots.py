from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from price_monitor.domain.enums import FailureKind
from price_monitor.fetchers.base import FetchError
from price_monitor.fetchers.http import HttpFetcher


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    robots_url: str
    crawl_delay_seconds: float | None


@dataclass(slots=True)
class _CacheEntry:
    parser: urllib.robotparser.RobotFileParser | None
    expires_at: float
    robots_url: str
    crawl_delay_seconds: float | None


class RobotsTxtPolicy:
    """Conservative, cached robots.txt enforcement using the trusted HTTP fetcher."""

    def __init__(self, *, user_agent: str, cache_seconds: float = 86_400) -> None:
        if cache_seconds < 0:
            raise ValueError("robots cache duration cannot be negative")
        self.user_agent = user_agent
        self.cache_seconds = cache_seconds
        self._cache: dict[str, _CacheEntry] = {}

    async def check(
        self,
        *,
        fetcher: HttpFetcher,
        url: str,
        allowed_hosts: tuple[str, ...],
    ) -> RobotsDecision:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        cache_key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        entry = self._cache.get(cache_key)
        if entry is None or entry.expires_at <= time.monotonic():
            entry = await self._load(
                fetcher=fetcher,
                robots_url=robots_url,
                allowed_hosts=allowed_hosts,
            )
            self._cache[cache_key] = entry
        if entry.crawl_delay_seconds is not None:
            fetcher.require_host_interval(host, entry.crawl_delay_seconds)
        allowed = entry.parser is None or entry.parser.can_fetch(self.user_agent, url)
        return RobotsDecision(
            allowed=allowed,
            robots_url=entry.robots_url,
            crawl_delay_seconds=entry.crawl_delay_seconds,
        )

    async def enforce(
        self,
        *,
        fetcher: HttpFetcher,
        url: str,
        allowed_hosts: tuple[str, ...],
    ) -> None:
        decision = await self.check(fetcher=fetcher, url=url, allowed_hosts=allowed_hosts)
        if not decision.allowed:
            raise FetchError(
                "robots.txt disallows this product URL",
                kind=FailureKind.ACCESS_DENIED,
                url=url,
                retryable=False,
            )

    async def _load(
        self,
        *,
        fetcher: HttpFetcher,
        robots_url: str,
        allowed_hosts: tuple[str, ...],
    ) -> _CacheEntry:
        try:
            page = await fetcher.fetch_text(robots_url, allowed_hosts=allowed_hosts)
        except FetchError as exc:
            if exc.kind == FailureKind.NOT_FOUND:
                return _CacheEntry(
                    parser=None,
                    expires_at=time.monotonic() + self.cache_seconds,
                    robots_url=robots_url,
                    crawl_delay_seconds=None,
                )
            raise

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(page.html.splitlines())
        crawl_delay = parser.crawl_delay(self.user_agent)
        if crawl_delay is None:
            crawl_delay = parser.crawl_delay("*")
        request_rate = parser.request_rate(self.user_agent) or parser.request_rate("*")
        rate_delay = (
            request_rate.seconds / request_rate.requests
            if request_rate is not None and request_rate.requests > 0
            else None
        )
        effective_delay = max(
            (value for value in (crawl_delay, rate_delay) if value is not None),
            default=None,
        )
        return _CacheEntry(
            parser=parser,
            expires_at=time.monotonic() + self.cache_seconds,
            robots_url=robots_url,
            crawl_delay_seconds=float(effective_delay) if effective_delay is not None else None,
        )
