from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import HttpUrl

from price_monitor.domain.enums import FailureKind
from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.fetchers.base import FetchError
from price_monitor.fetchers.policy import AddressResolver, URLPolicyError, system_resolver
from price_monitor.fetchers.policy import validate_public_url as enforce_public_url

if TYPE_CHECKING:
    from price_monitor.config import Settings


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
WallClock = Callable[[], datetime]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "content-language",
        "content-length",
        "content-type",
        "date",
        "etag",
        "last-modified",
        "retry-after",
    }
)
_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_CONTENT_TYPES = frozenset({"text/plain", "text/html", "application/octet-stream"})


class _HostRateLimiter:
    """Process-local start-time limiter, scoped by exact destination host."""

    def __init__(self, interval_seconds: float, *, sleep: Sleep, clock: Clock) -> None:
        self._interval_seconds = interval_seconds
        self._host_intervals: dict[str, float] = {}
        self._sleep = sleep
        self._clock = clock
        self._last_started: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        interval = max(self._interval_seconds, self._host_intervals.get(host, 0.0))
        if interval <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = self._clock()
            last_started = self._last_started.get(host)
            if last_started is not None:
                remaining = interval - (now - last_started)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last_started[host] = self._clock()

    def require_interval(self, host: str, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("host interval cannot be negative")
        self._host_intervals[host] = max(self._host_intervals.get(host, 0.0), seconds)


class HttpFetcher:
    """Bounded static-page fetcher with explicit redirects and SSRF checks.

    The class never falls back to a browser. A caller that intentionally chooses
    browser fetching must construct ``BrowserFetcher`` itself.
    """

    def __init__(
        self,
        *,
        user_agent: str = "PriceMonitorBeta/0.1 (+mailto:ops@example.invalid)",
        timeout_seconds: float = 15.0,
        maximum_response_bytes: int = 2_000_000,
        maximum_retries: int = 2,
        maximum_redirects: int = 5,
        backoff_base_seconds: float = 0.25,
        maximum_retry_after_seconds: float = 30.0,
        minimum_request_interval_seconds: float = 0.0,
        resolver: AddressResolver = system_resolver,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
        wall_clock: WallClock | None = None,
    ) -> None:
        if len(user_agent.strip()) < 10:
            raise ValueError("user_agent must descriptively identify the scraper")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if maximum_response_bytes <= 0:
            raise ValueError("maximum_response_bytes must be positive")
        if maximum_retries < 0:
            raise ValueError("maximum_retries cannot be negative")
        if maximum_redirects < 0:
            raise ValueError("maximum_redirects cannot be negative")
        if (
            backoff_base_seconds < 0
            or maximum_retry_after_seconds < 0
            or minimum_request_interval_seconds < 0
        ):
            raise ValueError("timing intervals cannot be negative")

        self.user_agent = user_agent.strip()
        self.timeout_seconds = timeout_seconds
        self.maximum_response_bytes = maximum_response_bytes
        self.maximum_retries = maximum_retries
        self.maximum_redirects = maximum_redirects
        self.backoff_base_seconds = backoff_base_seconds
        self.maximum_retry_after_seconds = maximum_retry_after_seconds
        self.resolver = resolver
        self._provided_client = client
        self._client: httpx.AsyncClient | None = client
        self._owns_client = client is None
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._limiter = _HostRateLimiter(
            minimum_request_interval_seconds,
            sleep=sleep,
            clock=clock,
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        **overrides: Any,
    ) -> HttpFetcher:
        options: dict[str, Any] = {
            "user_agent": settings.user_agent,
            "timeout_seconds": settings.request_timeout_seconds,
            "maximum_response_bytes": settings.maximum_response_bytes,
            "maximum_retries": settings.maximum_retries,
            "minimum_request_interval_seconds": (
                settings.default_minimum_request_interval_ms / 1_000
            ),
        }
        options.update(overrides)
        return cls(**options)

    async def __aenter__(self) -> HttpFetcher:
        await self._get_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(self.timeout_seconds),
                trust_env=False,
            )
        return self._client

    async def fetch_target(self, target: ScrapeTarget) -> FetchedPage:
        return await self.fetch(target.url, allowed_hosts=target.allowed_hosts)

    async def fetch(
        self,
        url: str | HttpUrl,
        *,
        allowed_hosts: Sequence[str],
    ) -> FetchedPage:
        requested_url = str(url)
        started = self._clock()
        last_error: FetchError | None = None

        for attempt in range(self.maximum_retries + 1):
            try:
                return await self._fetch_attempt(
                    requested_url,
                    requested_url=requested_url,
                    allowed_hosts=allowed_hosts,
                    started=started,
                    accepted_content_types=_HTML_CONTENT_TYPES,
                    accept_header="text/html,application/xhtml+xml;q=0.9",
                )
            except FetchError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.maximum_retries:
                    raise
                await self._sleep(self._retry_delay(exc, attempt))

        # The bounded loop always returns or raises; this keeps type checkers honest.
        assert last_error is not None
        raise last_error

    async def fetch_text(
        self,
        url: str | HttpUrl,
        *,
        allowed_hosts: Sequence[str],
    ) -> FetchedPage:
        """Fetch a bounded text resource, primarily a site's robots.txt."""

        requested_url = str(url)
        started = self._clock()
        last_error: FetchError | None = None
        for attempt in range(self.maximum_retries + 1):
            try:
                return await self._fetch_attempt(
                    requested_url,
                    requested_url=requested_url,
                    allowed_hosts=allowed_hosts,
                    started=started,
                    accepted_content_types=_TEXT_CONTENT_TYPES,
                    accept_header="text/plain,text/html;q=0.5,*/*;q=0.1",
                )
            except FetchError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.maximum_retries:
                    raise
                await self._sleep(self._retry_delay(exc, attempt))
        assert last_error is not None
        raise last_error

    def require_host_interval(self, host: str, seconds: float) -> None:
        self._limiter.require_interval(host.lower().rstrip("."), seconds)

    async def wait_for_host(self, host: str) -> None:
        """Apply the configured page-level delay to a separately rendered request."""

        await self._limiter.wait(host.lower().rstrip("."))

    async def _fetch_attempt(
        self,
        url: str,
        *,
        requested_url: str,
        allowed_hosts: Sequence[str],
        started: float,
        accepted_content_types: frozenset[str],
        accept_header: str,
    ) -> FetchedPage:
        current_url = url
        visited: set[str] = set()
        client = await self._get_client()

        for redirect_count in range(self.maximum_redirects + 1):
            if current_url in visited:
                raise FetchError(
                    "redirect loop detected",
                    url=current_url,
                    kind=FailureKind.TRANSPORT,
                )
            visited.add(current_url)

            try:
                checked = await enforce_public_url(
                    current_url,
                    allowed_hosts,
                    resolver=self.resolver,
                )
            except URLPolicyError as exc:
                raise FetchError(
                    f"outbound URL rejected: {exc}",
                    url=current_url,
                    kind=FailureKind.ACCESS_DENIED,
                ) from exc

            await self._limiter.wait(checked.host)
            try:
                response_context = client.stream(
                    "GET",
                    current_url,
                    headers={
                        "Accept": accept_header,
                        "User-Agent": self.user_agent,
                    },
                    follow_redirects=False,
                    timeout=self.timeout_seconds,
                )
                async with response_context as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError(
                                "redirect response omitted the Location header",
                                url=current_url,
                                status_code=response.status_code,
                            )
                        if redirect_count >= self.maximum_redirects:
                            raise FetchError(
                                "maximum redirect count exceeded",
                                url=current_url,
                                status_code=response.status_code,
                            )
                        redirected_url = urljoin(current_url, location)
                        if (
                            urlsplit(current_url).scheme.lower() == "https"
                            and urlsplit(redirected_url).scheme.lower() != "https"
                        ):
                            raise FetchError(
                                "HTTPS redirect downgrade is not permitted",
                                url=redirected_url,
                                status_code=response.status_code,
                                kind=FailureKind.ACCESS_DENIED,
                            )
                        current_url = redirected_url
                        continue

                    self._raise_for_status(
                        response.status_code,
                        current_url,
                        response.headers,
                    )
                    self._validate_content_headers(
                        response.headers,
                        current_url,
                        accepted_content_types=accepted_content_types,
                    )
                    body = await self._read_bounded(response, current_url)
                    encoding = response.encoding or "utf-8"
                    html = body.decode(encoding, errors="replace")
                    return FetchedPage(
                        requested_url=requested_url,
                        final_url=current_url,
                        html=html,
                        status_code=response.status_code,
                        fetched_at=datetime.now(UTC),
                        duration_ms=max(0, round((self._clock() - started) * 1_000)),
                        safe_headers=self._safe_headers(response.headers),
                        content_sha256=hashlib.sha256(body).hexdigest(),
                    )
            except FetchError:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise FetchError(
                    f"HTTP transport failed: {type(exc).__name__}",
                    url=current_url,
                    kind=FailureKind.TRANSPORT,
                    retryable=True,
                ) from exc

        raise FetchError("maximum redirect count exceeded", url=current_url)

    def _validate_content_headers(
        self,
        headers: Mapping[str, str],
        url: str,
        *,
        accepted_content_types: frozenset[str],
    ) -> None:
        media_type = headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
        if media_type not in accepted_content_types:
            label = media_type or "missing"
            raise FetchError(
                f"unsupported response Content-Type: {label}",
                url=url,
                kind=FailureKind.EXTRACTION,
            )
        raw_length = headers.get("content-length")
        if raw_length:
            try:
                declared_length = int(raw_length)
            except ValueError as exc:
                raise FetchError("invalid response Content-Length", url=url) from exc
            if declared_length < 0:
                raise FetchError("invalid response Content-Length", url=url)
            if declared_length > self.maximum_response_bytes:
                raise FetchError(
                    "response exceeds the configured byte limit",
                    url=url,
                    kind=FailureKind.EXTRACTION,
                )

    async def _read_bounded(self, response: httpx.Response, url: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.maximum_response_bytes:
                raise FetchError(
                    "response exceeds the configured byte limit",
                    url=url,
                    kind=FailureKind.EXTRACTION,
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
        return {
            key.lower(): value[:1_000]
            for key, value in headers.items()
            if key.lower() in _SAFE_RESPONSE_HEADERS
        }

    def _retry_delay(self, error: FetchError, attempt: int) -> float:
        exponential_backoff = self.backoff_base_seconds * (2**attempt)
        return float(max(exponential_backoff, error.retry_after_seconds or 0.0))

    def _parse_retry_after(self, value: str | None) -> float | None:
        """Return a bounded Retry-After delay, or ``None`` when it is unsafe."""

        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            return None

        if candidate.isascii() and candidate.isdigit():
            # Avoid spending work parsing an attacker-controlled, unbounded integer.
            if len(candidate) > 10:
                return None
            delay_seconds = int(candidate)
            if delay_seconds > self.maximum_retry_after_seconds:
                return None
            delay = float(delay_seconds)
        else:
            try:
                retry_at = parsedate_to_datetime(candidate)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            try:
                delay = max(
                    0.0,
                    (retry_at.astimezone(UTC) - self._wall_clock().astimezone(UTC)).total_seconds(),
                )
            except (OverflowError, ValueError):
                return None

        if delay > self.maximum_retry_after_seconds:
            return None
        return delay

    def _raise_for_status(
        self,
        status_code: int,
        url: str,
        headers: Mapping[str, str],
    ) -> None:
        if 200 <= status_code < 300:
            return
        retry_after_seconds: float | None = None
        if status_code == 404:
            kind = FailureKind.NOT_FOUND
        elif status_code == 429:
            kind = FailureKind.RATE_LIMITED
            retry_after_seconds = self._parse_retry_after(headers.get("retry-after"))
        elif status_code in {401, 403}:
            kind = FailureKind.ACCESS_DENIED
        else:
            kind = FailureKind.TRANSPORT
        raise FetchError(
            f"upstream returned HTTP {status_code}",
            url=url,
            status_code=status_code,
            kind=kind,
            retryable=(
                status_code in _RETRYABLE_STATUSES
                and (status_code != 429 or retry_after_seconds is not None)
            ),
            retry_after_seconds=retry_after_seconds,
        )


# Backwards-friendly spelling for callers that prefer the conventional acronym.
HTTPFetcher = HttpFetcher
