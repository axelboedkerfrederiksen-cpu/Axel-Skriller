from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import HttpUrl

from price_monitor.domain.enums import FailureKind
from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.fetchers.base import FetchError
from price_monitor.fetchers.policy import AddressResolver, URLPolicyError, system_resolver
from price_monitor.fetchers.policy import validate_public_url as enforce_public_url


class BrowserUnavailableError(FetchError):
    """The explicitly selected optional browser transport is not installed."""


class BrowserFetcher:
    """Explicit Playwright transport for JavaScript-only pages.

    Playwright is imported only inside ``fetch``. Merely importing price-monitor
    therefore never requires the optional browser dependency, and HTTP fetching
    never invokes this class as a fallback.
    """

    def __init__(
        self,
        *,
        user_agent: str = "PriceMonitorBeta/0.1 (+mailto:ops@example.invalid)",
        timeout_seconds: float = 30.0,
        maximum_response_bytes: int = 2_000_000,
        resolver: AddressResolver = system_resolver,
        browser_name: str = "chromium",
    ) -> None:
        if len(user_agent.strip()) < 10:
            raise ValueError("user_agent must descriptively identify the scraper")
        if timeout_seconds <= 0 or maximum_response_bytes <= 0:
            raise ValueError("browser fetch limits must be positive")
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise ValueError("unsupported Playwright browser")
        self.user_agent = user_agent.strip()
        self.timeout_seconds = timeout_seconds
        self.maximum_response_bytes = maximum_response_bytes
        self.resolver = resolver
        self.browser_name = browser_name

    async def fetch_target(self, target: ScrapeTarget) -> FetchedPage:
        return await self.fetch(target.url, allowed_hosts=target.allowed_hosts)

    async def fetch(
        self,
        url: str | HttpUrl,
        *,
        allowed_hosts: Sequence[str],
    ) -> FetchedPage:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise BrowserUnavailableError(
                "browser fetching was requested, but the optional Playwright dependency "
                "is not installed",
                kind=FailureKind.INTERNAL,
                url=str(url),
            ) from exc

        requested_url = str(url)
        try:
            await enforce_public_url(
                requested_url,
                allowed_hosts,
                resolver=self.resolver,
            )
        except URLPolicyError as exc:
            raise FetchError(
                f"outbound URL rejected: {exc}",
                kind=FailureKind.ACCESS_DENIED,
                url=requested_url,
            ) from exc

        started = time.monotonic()
        blocked_document: list[str] = []
        async with async_playwright() as playwright:
            browser_type = getattr(playwright, self.browser_name)
            browser = await browser_type.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=self.user_agent)
                page = await context.new_page()

                async def guard_request(route: Any, request: Any) -> None:
                    try:
                        await enforce_public_url(
                            request.url,
                            allowed_hosts,
                            resolver=self.resolver,
                        )
                    except URLPolicyError:
                        if request.is_navigation_request():
                            blocked_document.append(request.url)
                        await route.abort("blockedbyclient")
                        return
                    await route.continue_()

                await page.route("**/*", guard_request)
                try:
                    response = await page.goto(
                        requested_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_seconds * 1_000,
                    )
                except Exception as exc:  # Playwright types are optional at import time.
                    if blocked_document:
                        raise FetchError(
                            "browser navigation attempted a disallowed redirect",
                            kind=FailureKind.ACCESS_DENIED,
                            url=blocked_document[-1],
                        ) from exc
                    raise FetchError(
                        f"browser navigation failed: {type(exc).__name__}",
                        kind=FailureKind.TRANSPORT,
                        url=requested_url,
                        retryable=True,
                    ) from exc
                if response is None:
                    raise FetchError(
                        "browser navigation returned no document response",
                        kind=FailureKind.TRANSPORT,
                        url=requested_url,
                    )
                final_url = page.url
                try:
                    await enforce_public_url(
                        final_url,
                        allowed_hosts,
                        resolver=self.resolver,
                    )
                except URLPolicyError as exc:
                    raise FetchError(
                        f"browser final URL rejected: {exc}",
                        kind=FailureKind.ACCESS_DENIED,
                        url=final_url,
                    ) from exc

                if not 200 <= response.status < 300:
                    raise FetchError(
                        f"upstream returned HTTP {response.status}",
                        kind=FailureKind.TRANSPORT,
                        url=final_url,
                        status_code=response.status,
                    )
                html = await page.content()
                body = html.encode("utf-8")
                if len(body) > self.maximum_response_bytes:
                    raise FetchError(
                        "rendered page exceeds the configured byte limit",
                        kind=FailureKind.EXTRACTION,
                        url=final_url,
                    )
                response_headers = await response.all_headers()
                safe_headers = {
                    key.lower(): value[:1_000]
                    for key, value in response_headers.items()
                    if key.lower()
                    in {
                        "cache-control",
                        "content-language",
                        "content-length",
                        "content-type",
                        "date",
                        "etag",
                        "last-modified",
                    }
                }
                return FetchedPage(
                    requested_url=requested_url,
                    final_url=final_url,
                    html=html,
                    status_code=response.status,
                    fetched_at=datetime.now(UTC),
                    duration_ms=max(0, round((time.monotonic() - started) * 1_000)),
                    safe_headers=safe_headers,
                    content_sha256=hashlib.sha256(body).hexdigest(),
                )
            finally:
                await browser.close()
