"""Deterministic site scraper adapters."""

from price_monitor.scrapers.base import ScraperAdapter, ScraperError, ScraperExtractionError
from price_monitor.scrapers.parsing import (
    MoneyParseError,
    detect_currency,
    normalize_text,
    parse_availability,
    parse_money,
)
from price_monitor.scrapers.selector import DeterministicScraper, SelectorScraper
from price_monitor.scrapers.spec import SelectorRule, SiteSpec

__all__ = [
    "DeterministicScraper",
    "MoneyParseError",
    "ScraperAdapter",
    "ScraperError",
    "ScraperExtractionError",
    "SelectorRule",
    "SelectorScraper",
    "SiteSpec",
    "detect_currency",
    "normalize_text",
    "parse_availability",
    "parse_money",
]
