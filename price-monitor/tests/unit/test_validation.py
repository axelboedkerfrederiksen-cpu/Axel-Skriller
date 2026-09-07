from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from price_monitor.domain.enums import Availability, FetchMode
from price_monitor.domain.types import ExtractedProduct, FieldEvidence, ScrapeTarget
from price_monitor.services.validation import ProductValidator, validate_extracted_product


def target(**changes: object) -> ScrapeTarget:
    values: dict[str, object] = {
        "competitor_product_id": "competitor-product-1",
        "url": "https://books.toscrape.com/catalogue/example/index.html",
        "allowed_hosts": ("books.toscrape.com",),
        "adapter_key": "books_to_scrape",
        "adapter_revision": "1",
        "fetch_mode": FetchMode.HTTP,
        "expected_name": "A Light in the Attic",
        "expected_external_id": "a897fe39b1053632",
        "expected_currency": "GBP",
        "minimum_valid_price": Decimal("1"),
        "maximum_valid_price": Decimal("100"),
        "previous_price": Decimal("50"),
        "previous_currency": "GBP",
        "maximum_price_change_ratio": Decimal("0.80"),
    }
    values.update(changes)
    return ScrapeTarget.model_validate(values)


def product(**changes: object) -> ExtractedProduct:
    context = "A Light in the Attic £51.77 In stock"
    values: dict[str, object] = {
        "name": "A Light in the Attic",
        "price": Decimal("51.77"),
        "currency": "GBP",
        "availability": Availability.IN_STOCK,
        "product_url": "https://books.toscrape.com/catalogue/example/index.html",
        "external_product_id": "a897fe39b1053632",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "evidence": {
            "name": FieldEvidence(
                source="css",
                selector="h1",
                raw_value="A Light in the Attic",
                container_text=context,
            ),
            "price": FieldEvidence(
                source="css",
                selector=".price_color",
                raw_value="£51.77",
                container_text=context,
            ),
            "currency": FieldEvidence(
                source="derived",
                selector=".price_color",
                raw_value="£51.77",
                container_text=context,
            ),
        },
    }
    values.update(changes)
    return ExtractedProduct.model_validate(values)


def error_codes(outcome: object) -> set[str]:
    assert hasattr(outcome, "issues")
    return {issue.code for issue in outcome.issues if issue.severity == "error"}


def test_valid_product_is_accepted() -> None:
    outcome = validate_extracted_product(product(), target())

    assert outcome.accepted
    assert outcome.issues == ()
    assert outcome.primary_failure_kind is None


def test_implausible_price_and_large_change_are_rejected() -> None:
    outcome = ProductValidator().validate(product(price=Decimal("501")), target())

    assert not outcome.accepted
    assert {"price_above_maximum", "price_change_too_large"} <= error_codes(outcome)


def test_identity_currency_and_exact_host_are_validated() -> None:
    outcome = validate_extracted_product(
        product(
            name="Completely Different Item",
            currency="USD",
            external_product_id="wrong",
            product_url="https://cdn.books.toscrape.com/item",
        ),
        target(),
    )

    assert not outcome.accepted
    assert {
        "product_url_host_mismatch",
        "product_name_mismatch",
        "external_id_mismatch",
        "currency_mismatch",
        "currency_changed_unexpectedly",
    } <= error_codes(outcome)


def test_missing_or_fabricated_evidence_is_rejected() -> None:
    item = product()
    invalid_evidence = {
        "name": item.evidence["name"],
        "price": item.evidence["price"].model_copy(update={"raw_value": "£9.99"}),
    }
    outcome = validate_extracted_product(
        item.model_copy(update={"evidence": invalid_evidence}),
        target(),
    )

    assert not outcome.accepted
    assert {"currency_evidence_missing", "price_evidence_mismatch"} <= error_codes(outcome)


def test_price_context_without_visible_value_is_a_warning() -> None:
    item = product()
    evidence = dict(item.evidence)
    evidence["price"] = evidence["price"].model_copy(
        update={"container_text": "A Light in the Attic"}
    )

    outcome = validate_extracted_product(item.model_copy(update={"evidence": evidence}), target())

    assert outcome.accepted
    assert [issue.code for issue in outcome.issues] == ["price_context_weak"]
