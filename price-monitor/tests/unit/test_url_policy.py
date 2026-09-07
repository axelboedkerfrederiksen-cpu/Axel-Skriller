from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from price_monitor.domain.enums import FailureKind
from price_monitor.fetchers import FetchError, HttpFetcher, URLPolicyError
from price_monitor.fetchers.policy import is_public_ip, validate_public_url, validate_url_syntax

PUBLIC_IP = "93.184.216.34"


def test_host_allowlist_is_exact_not_suffix_based() -> None:
    validate_url_syntax("https://shop.example/product", ("shop.example",))

    with pytest.raises(URLPolicyError, match="not explicitly allowed"):
        validate_url_syntax("https://cdn.shop.example/product", ("shop.example",))
    with pytest.raises(URLPolicyError, match="not explicitly allowed"):
        validate_url_syntax("https://shop.example.evil.test/product", ("shop.example",))


def test_url_policy_rejects_credentials_and_nonstandard_ports() -> None:
    with pytest.raises(URLPolicyError, match="credentials"):
        validate_url_syntax("https://user@shop.example/item", ("shop.example",))
    with pytest.raises(URLPolicyError, match="port 8443"):
        validate_url_syntax("https://shop.example:8443/item", ("shop.example",))


def test_all_dns_answers_must_be_public() -> None:
    async def mixed_resolver(_host: str, _port: int) -> list[str]:
        return [PUBLIC_IP, "127.0.0.1"]

    with pytest.raises(URLPolicyError, match="non-public"):
        asyncio.run(
            validate_public_url(
                "https://shop.example/item",
                ("shop.example",),
                resolver=mixed_resolver,
            )
        )

    assert is_public_ip(PUBLIC_IP)
    assert not is_public_ip("10.0.0.1")
    assert not is_public_ip("::ffff:127.0.0.1")


def test_http_fetcher_checks_redirect_host_before_following() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://private.example/admin"})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(client=client, resolver=lambda *_: [PUBLIC_IP])
            with pytest.raises(FetchError) as raised:
                await fetcher.fetch(
                    "https://shop.example/item",
                    allowed_hosts=("shop.example",),
                )
            assert raised.value.kind is FailureKind.ACCESS_DENIED

    asyncio.run(scenario())
    assert requests == ["https://shop.example/item"]


def test_http_fetcher_follows_only_validated_redirects_and_records_safe_metadata() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/old":
            return httpx.Response(302, headers={"Location": "/new"})
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "ETag": '"fixture"',
                "Set-Cookie": "secret=value",
            },
            content=b"<html><h1>Safe</h1></html>",
        )

    async def scenario() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(client=client, resolver=lambda *_: [PUBLIC_IP])
            return await fetcher.fetch(
                "https://shop.example/old",
                allowed_hosts=("shop.example",),
            )

    page = asyncio.run(scenario())
    assert str(page.final_url) == "https://shop.example/new"
    assert page.html == "<html><h1>Safe</h1></html>"
    assert page.safe_headers["etag"] == '"fixture"'
    assert "set-cookie" not in page.safe_headers
    assert requests[-1].headers["user-agent"].startswith("PriceMonitorBeta/")


def test_http_fetcher_retries_transport_errors_with_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("fixture failure", request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html>ok</html>",
        )

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(
                client=client,
                resolver=lambda *_: [PUBLIC_IP],
                maximum_retries=2,
                backoff_base_seconds=0.1,
                sleep=fake_sleep,
            )
            page = await fetcher.fetch(
                "https://shop.example/item",
                allowed_hosts=("shop.example",),
            )
            assert page.status_code == 200

    asyncio.run(scenario())
    assert attempts == 3
    assert delays == pytest.approx([0.1, 0.2])


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        ("7", 7.0),
        (
            format_datetime(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), usegmt=True),
            5.0,
        ),
    ],
)
def test_http_fetcher_honors_bounded_retry_after(
    retry_after: str,
    expected_delay: float,
) -> None:
    attempts = 0
    delays: list[float] = []
    now = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html>ok</html>",
        )

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(
                client=client,
                resolver=lambda *_: [PUBLIC_IP],
                maximum_retries=1,
                backoff_base_seconds=0.1,
                maximum_retry_after_seconds=10,
                sleep=fake_sleep,
                wall_clock=lambda: now,
            )
            page = await fetcher.fetch(
                "https://shop.example/item",
                allowed_hosts=("shop.example",),
            )
            assert page.status_code == 200

    asyncio.run(scenario())
    assert attempts == 2
    assert delays == pytest.approx([expected_delay])


@pytest.mark.parametrize(
    "retry_after",
    [
        None,
        "not-a-delay",
        "31",
        "9" * 5_000,
        format_datetime(
            datetime(2026, 1, 2, 3, 4, tzinfo=UTC) + timedelta(seconds=31),
            usegmt=True,
        ),
    ],
)
def test_http_fetcher_does_not_retry_429_without_safe_retry_after(
    retry_after: str | None,
) -> None:
    attempts = 0
    delays: list[float] = []
    now = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        return httpx.Response(429, headers=headers)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(
                client=client,
                resolver=lambda *_: [PUBLIC_IP],
                maximum_retries=2,
                maximum_retry_after_seconds=30,
                sleep=fake_sleep,
                wall_clock=lambda: now,
            )
            with pytest.raises(FetchError) as raised:
                await fetcher.fetch(
                    "https://shop.example/item",
                    allowed_hosts=("shop.example",),
                )
            assert raised.value.kind is FailureKind.RATE_LIMITED
            assert not raised.value.retryable

    asyncio.run(scenario())
    assert attempts == 1
    assert delays == []


@pytest.mark.parametrize(
    ("headers", "content", "message"),
    [
        ({"Content-Type": "application/json"}, b"{}", "Content-Type"),
        ({"Content-Type": "text/html"}, b"0123456789", "byte limit"),
    ],
)
def test_http_fetcher_enforces_content_type_and_size(
    headers: dict[str, str],
    content: bytes,
    message: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=content)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = HttpFetcher(
                client=client,
                resolver=lambda *_: [PUBLIC_IP],
                maximum_response_bytes=5,
            )
            with pytest.raises(FetchError, match=message):
                await fetcher.fetch(
                    "https://shop.example/item",
                    allowed_hosts=("shop.example",),
                )

    asyncio.run(scenario())
