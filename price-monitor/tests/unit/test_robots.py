from __future__ import annotations

import asyncio

import httpx
import pytest

from price_monitor.fetchers import FetchError, HttpFetcher, RobotsTxtPolicy

PUBLIC_IP = "93.184.216.34"


def test_robots_policy_blocks_disallowed_path_and_caches_rules() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="User-agent: *\nDisallow: /private/\nCrawl-delay: 2\n",
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(
                client=client,
                resolver=lambda *_: [PUBLIC_IP],
                minimum_request_interval_seconds=0,
                sleep=lambda _: _completed(),
            )
            policy = RobotsTxtPolicy(user_agent="PriceMonitorBeta/0.1")
            with pytest.raises(FetchError, match=r"robots\.txt disallows"):
                await policy.enforce(
                    fetcher=fetcher,
                    url="https://shop.example/private/item",
                    allowed_hosts=("shop.example",),
                )
            decision = await policy.check(
                fetcher=fetcher,
                url="https://shop.example/public/item",
                allowed_hosts=("shop.example",),
            )
            assert decision.allowed
            assert decision.crawl_delay_seconds == 2

    asyncio.run(scenario())
    assert calls == 1


async def _completed() -> None:
    return None
