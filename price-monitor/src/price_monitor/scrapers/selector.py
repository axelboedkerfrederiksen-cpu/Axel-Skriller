from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bs4 import BeautifulSoup, Tag
from soupsieve import SelectorSyntaxError

from price_monitor.domain.enums import Availability
from price_monitor.domain.types import ExtractedProduct, FetchedPage, FieldEvidence
from price_monitor.scrapers.base import ScraperExtractionError
from price_monitor.scrapers.parsing import (
    MoneyParseError,
    apply_pattern,
    detect_currency,
    normalize_text,
    parse_availability,
    parse_money,
)
from price_monitor.scrapers.spec import SelectorRule, SiteSpec


@dataclass(frozen=True, slots=True)
class _Selection:
    value: str
    raw_value: str
    selector: str
    attribute: str | None
    source: Literal["css", "attribute", "meta"]


class SelectorScraper:
    """Pure declarative scraper backed only by a frozen ``SiteSpec``."""

    def __init__(self, spec: SiteSpec) -> None:
        self.spec = spec

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def revision(self) -> str:
        return self.spec.revision

    def extract(self, page: FetchedPage) -> ExtractedProduct:
        soup = BeautifulSoup(page.html, "lxml")
        try:
            container = soup.select_one(self.spec.product_container)
        except SelectorSyntaxError as exc:
            raise ScraperExtractionError(
                "product container selector is invalid",
                field="product_container",
                selector_attempts=(self.spec.product_container,),
            ) from exc
        if container is None:
            raise ScraperExtractionError(
                "product container was not found",
                field="product_container",
                selector_attempts=(self.spec.product_container,),
            )

        container_text = self._bounded(normalize_text(container.get_text(" ", strip=True)), 4_000)
        name_match = self._required("name", self.spec.name, container, soup)
        price_match = self._required("price", self.spec.price, container, soup)
        name = normalize_text(name_match.value)
        if not name:
            raise ScraperExtractionError("product name was empty", field="name")
        try:
            price = parse_money(price_match.value)
        except MoneyParseError as exc:
            raise ScraperExtractionError(
                f"price could not be parsed: {exc}",
                field="price",
                selector_attempts=(price_match.selector,),
            ) from exc

        currency_match = self._optional(self.spec.currency, container, soup)
        explicit_currency = (
            detect_currency(currency_match.value, self.spec.currency_symbol_map)
            if currency_match
            else None
        )
        price_currency = detect_currency(price_match.value, self.spec.currency_symbol_map)
        if explicit_currency and price_currency and explicit_currency != price_currency:
            assert currency_match is not None
            raise ScraperExtractionError(
                "currency selector conflicts with the price field",
                field="currency",
                selector_attempts=(currency_match.selector,),
            )
        currency = explicit_currency or price_currency
        if currency is None:
            raise ScraperExtractionError(
                "currency could not be determined",
                field="currency",
                selector_attempts=tuple(rule.selector for rule in self.spec.currency),
            )

        availability_match = self._optional(self.spec.availability, container, soup)
        availability = (
            parse_availability(
                availability_match.value,
                in_stock_terms=self.spec.in_stock_terms,
                out_of_stock_terms=self.spec.out_of_stock_terms,
                preorder_terms=self.spec.preorder_terms,
            )
            if availability_match
            else Availability.UNKNOWN
        )
        external_id_match = self._optional(self.spec.external_product_id, container, soup)
        external_id = normalize_text(external_id_match.value) if external_id_match else None

        evidence: dict[str, FieldEvidence] = {
            "name": self._evidence(name_match, container_text),
            "price": self._evidence(price_match, container_text),
            "currency": (
                self._evidence(currency_match, container_text)
                if currency_match
                else FieldEvidence(
                    source="derived",
                    selector=price_match.selector,
                    attribute=price_match.attribute,
                    raw_value=self._bounded(price_match.raw_value, 2_000),
                    container_text=container_text,
                )
            ),
            "availability": (
                self._evidence(availability_match, container_text)
                if availability_match
                else FieldEvidence(
                    source="derived",
                    raw_value="",
                    container_text=container_text,
                )
            ),
            "product_url": FieldEvidence(
                source="derived",
                raw_value=self._bounded(str(page.final_url), 2_000),
                container_text=container_text,
            ),
        }
        if external_id_match:
            evidence["external_product_id"] = self._evidence(
                external_id_match,
                container_text,
            )

        return ExtractedProduct(
            name=name,
            price=price,
            currency=currency,
            availability=availability,
            product_url=page.final_url,
            external_product_id=external_id or None,
            observed_at=page.fetched_at,
            evidence=evidence,
        )

    # ``scrape`` is deliberately an alias for compatibility with adapter callers;
    # it remains pure and performs no fetching.
    def scrape(self, page: FetchedPage) -> ExtractedProduct:
        return self.extract(page)

    def _required(
        self,
        field: str,
        rules: tuple[SelectorRule, ...],
        container: Tag,
        soup: BeautifulSoup,
    ) -> _Selection:
        selection = self._optional(rules, container, soup)
        if selection is None:
            raise ScraperExtractionError(
                f"{field} selector did not produce a value",
                field=field,
                selector_attempts=tuple(rule.selector for rule in rules),
            )
        return selection

    def _optional(
        self,
        rules: tuple[SelectorRule, ...],
        container: Tag,
        soup: BeautifulSoup,
    ) -> _Selection | None:
        for rule in rules:
            selection = self._select(rule, container, soup)
            if selection is not None:
                return selection
        return None

    def _select(
        self,
        rule: SelectorRule,
        container: Tag,
        soup: BeautifulSoup,
    ) -> _Selection | None:
        node: Tag | None
        if rule.source == "meta":
            node = self._select_meta(soup, rule.selector)
        else:
            try:
                selected = container.select_one(rule.selector)
            except SelectorSyntaxError:
                return None
            node = selected if isinstance(selected, Tag) else None
        if node is None:
            return None

        attribute = rule.attribute or ("content" if rule.source == "meta" else None)
        if attribute:
            raw_attribute = node.get(attribute)
            if isinstance(raw_attribute, list):
                raw = " ".join(str(part) for part in raw_attribute)
            elif raw_attribute is None:
                return None
            else:
                raw = str(raw_attribute)
        else:
            raw = node.get_text(" ", strip=True)
        raw = normalize_text(raw)
        if not raw:
            return None
        matched = apply_pattern(raw, rule.pattern)
        if matched is None:
            return None
        value = normalize_text(matched)
        if not value:
            return None
        evidence_source: Literal["css", "attribute", "meta"]
        if rule.source == "meta":
            evidence_source = "meta"
        elif attribute:
            evidence_source = "attribute"
        else:
            evidence_source = "css"
        return _Selection(
            value=value,
            raw_value=raw,
            selector=rule.selector,
            attribute=attribute,
            source=evidence_source,
        )

    @staticmethod
    def _select_meta(soup: BeautifulSoup, selector: str) -> Tag | None:
        # Specs may use either an explicit CSS selector or a concise metadata key.
        try:
            selected = soup.select_one(selector)
        except SelectorSyntaxError:
            selected = None
        if isinstance(selected, Tag) and selected.name == "meta":
            return selected
        for attribute in ("property", "name", "itemprop"):
            found = soup.find("meta", attrs={attribute: selector})
            if isinstance(found, Tag):
                return found
        return None

    @classmethod
    def _evidence(cls, selection: _Selection, container_text: str) -> FieldEvidence:
        return FieldEvidence(
            source=selection.source,
            selector=selection.selector,
            attribute=selection.attribute,
            raw_value=cls._bounded(selection.raw_value, 2_000),
            container_text=container_text,
        )

    @staticmethod
    def _bounded(value: str, limit: int) -> str:
        return value if len(value) <= limit else value[:limit]


DeterministicScraper = SelectorScraper
