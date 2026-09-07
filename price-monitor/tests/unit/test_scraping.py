from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from price_monitor.domain.enums import Availability
from price_monitor.domain.types import FetchedPage
from price_monitor.fetchers import looks_like_anti_bot_interstitial
from price_monitor.scrapers import (
    ScraperExtractionError,
    SelectorRule,
    SelectorScraper,
    SiteSpec,
    detect_currency,
    parse_availability,
    parse_money,
)
from price_monitor.scrapers.sites.books_to_scrape import BOOKS_TO_SCRAPE_V1

FIXTURES = Path(__file__).parents[1] / "fixtures" / "books_to_scrape"


def test_challenge_pages_are_detected_without_false_positive_on_product_fixture() -> None:
    assert looks_like_anti_bot_interstitial(
        "<html><title>Just a moment...</title><div class='cf-chl-widget'></div></html>"
    )
    assert not looks_like_anti_bot_interstitial(
        (FIXTURES / "a-light-in-the-attic.html").read_text(encoding="utf-8")
    )


def fetched_fixture(name: str) -> FetchedPage:
    body = (FIXTURES / name).read_bytes()
    return FetchedPage(
        requested_url=f"https://books.toscrape.com/catalogue/{name}",
        final_url=f"https://books.toscrape.com/catalogue/{name}",
        html=body.decode(),
        status_code=200,
        fetched_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        duration_ms=12,
        safe_headers={"content-type": "text/html; charset=utf-8"},
        content_sha256=hashlib.sha256(body).hexdigest(),
    )


@pytest.mark.parametrize(
    ("fixture", "name", "price", "external_id"),
    [
        (
            "a-light-in-the-attic.html",
            "A Light in the Attic",
            Decimal("51.77"),
            "a897fe39b1053632",
        ),
        (
            "tipping-the-velvet.html",
            "Tipping the Velvet",
            Decimal("53.74"),
            "90fa61229261140a",
        ),
    ],
)
def test_books_to_scrape_fixture_extraction(
    fixture: str,
    name: str,
    price: Decimal,
    external_id: str,
) -> None:
    product = SelectorScraper(BOOKS_TO_SCRAPE_V1).extract(fetched_fixture(fixture))

    assert product.name == name
    assert product.price == price
    assert product.currency == "GBP"
    assert product.availability is Availability.IN_STOCK
    assert product.external_product_id == external_id
    assert product.observed_at == datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    assert product.evidence["name"].selector == ".product_main h1"
    assert product.evidence["price"].raw_value == f"£{price}"
    assert name in (product.evidence["price"].container_text or "")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,234.56", Decimal("1234.56")),
        ("1.234,56 €", Decimal("1234.56")),
        ("DKK 1\u202f234,50", Decimal("1234.50")),
        ("CHF 1\u2019234.50", Decimal("1234.50")),
        ("£1.234", Decimal("1234")),
    ],
)
def test_parse_money_supports_common_locale_formats(raw: str, expected: Decimal) -> None:
    assert parse_money(raw) == expected


def test_currency_and_stock_parsing_are_deterministic() -> None:
    assert detect_currency("Price: 14,95 kr.", {"kr.": "DKK"}) == "DKK"
    assert parse_availability("https://schema.org/OutOfStock") is Availability.OUT_OF_STOCK
    assert parse_availability("Pre-order for October") is Availability.PREORDER
    assert parse_availability("0 items in stock") is Availability.OUT_OF_STOCK


def test_selector_fallback_and_meta_attribute_evidence() -> None:
    body = b"""<html><head><meta property='product:price:currency' content='EUR'></head>
    <body><main class='product'><h1>Locale Lamp</h1><span data-price='1.234,50'></span>
    <link itemprop='availability' href='https://schema.org/OutOfStock'></main></body></html>"""
    page = FetchedPage(
        requested_url="https://shop.example/products/lamp",
        final_url="https://shop.example/products/lamp",
        html=body.decode(),
        status_code=200,
        duration_ms=1,
        content_sha256=hashlib.sha256(body).hexdigest(),
    )
    spec = SiteSpec(
        key="locale_shop",
        revision="1",
        allowed_hosts=("shop.example",),
        product_container="main.product",
        name=(SelectorRule(selector=".missing"), SelectorRule(selector="h1")),
        price=(SelectorRule(selector="[data-price]", attribute="data-price"),),
        currency=(SelectorRule(selector="product:price:currency", source="meta"),),
        availability=(SelectorRule(selector="[itemprop=availability]", attribute="href"),),
    )

    product = SelectorScraper(spec).extract(page)

    assert product.price == Decimal("1234.50")
    assert product.currency == "EUR"
    assert product.availability is Availability.OUT_OF_STOCK
    assert product.evidence["price"].source == "attribute"
    assert product.evidence["currency"].source == "meta"


def test_missing_product_container_is_an_auditable_extraction_error() -> None:
    page = fetched_fixture("a-light-in-the-attic.html")
    broken = BOOKS_TO_SCRAPE_V1.model_copy(update={"product_container": "#removed"})

    with pytest.raises(ScraperExtractionError) as raised:
        SelectorScraper(broken).extract(page)

    assert raised.value.field == "product_container"
    assert raised.value.selector_attempts == ("#removed",)
