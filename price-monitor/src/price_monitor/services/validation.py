from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from price_monitor.domain.enums import FailureKind
from price_monitor.domain.types import (
    ExtractedProduct,
    ScrapeTarget,
    ValidationIssue,
    ValidationOutcome,
)
from price_monitor.fetchers.policy import URLPolicyError, canonicalize_host
from price_monitor.scrapers.parsing import MoneyParseError, normalize_text, parse_money

# Active ISO 4217 codes plus fund/metal/test codes commonly returned by shops.
# XXX intentionally remains invalid: it means "no currency" rather than a price.
_CURRENCY_CODES_TEXT = (
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND "
    "BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU "
    "CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS "
    "GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD "
    "JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL "
    "MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR "
    "NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG "
    "SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY "
    "TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XAG "
    "XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA YER ZAR ZMW ZWL"
)
KNOWN_CURRENCY_CODES = frozenset(_CURRENCY_CODES_TEXT.split())


def _issue(
    code: str,
    message: str,
    failure_kind: FailureKind,
    *,
    severity: str = "error",
    **context: object,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity="warning" if severity == "warning" else "error",
        failure_kind=failure_kind,
        context={key: value for key, value in context.items() if value is not None},
    )


def _normalized_identity(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalize_text(value).casefold()))


def _identity_score(expected: str, actual: str) -> float:
    normalized_expected = _normalized_identity(expected)
    normalized_actual = _normalized_identity(actual)
    if not normalized_expected or not normalized_actual:
        return 0.0
    if normalized_expected in normalized_actual or normalized_actual in normalized_expected:
        return 1.0
    expected_tokens = set(normalized_expected.split())
    actual_tokens = set(normalized_actual.split())
    token_score = len(expected_tokens & actual_tokens) / len(expected_tokens | actual_tokens)
    sequence_score = SequenceMatcher(None, normalized_expected, normalized_actual).ratio()
    return max(token_score, sequence_score)


class ProductValidator:
    """Deterministic acceptance gate for scraped product observations."""

    def __init__(self, *, minimum_name_similarity: float = 0.65) -> None:
        if not 0 <= minimum_name_similarity <= 1:
            raise ValueError("minimum_name_similarity must be between zero and one")
        self.minimum_name_similarity = minimum_name_similarity

    def validate(
        self,
        product: ExtractedProduct,
        target: ScrapeTarget,
    ) -> ValidationOutcome:
        issues: list[ValidationIssue] = []

        self._validate_schema(product, issues)
        self._validate_price(product, target, issues)
        self._validate_identity(product, target, issues)
        self._validate_evidence(product, issues)

        return ValidationOutcome(
            accepted=not any(issue.severity == "error" for issue in issues),
            issues=tuple(issues),
        )

    @staticmethod
    def _validate_schema(
        product: ExtractedProduct,
        issues: list[ValidationIssue],
    ) -> None:
        if not normalize_text(product.name):
            issues.append(_issue("name_empty", "product name is empty", FailureKind.SCHEMA))
        if not product.price.is_finite():
            issues.append(_issue("price_not_finite", "price must be finite", FailureKind.SCHEMA))
        if product.currency not in KNOWN_CURRENCY_CODES:
            issues.append(
                _issue(
                    "currency_unknown",
                    "currency is not a recognized ISO 4217 code",
                    FailureKind.SCHEMA,
                    currency=product.currency,
                )
            )
        if product.observed_at.tzinfo is None or product.observed_at.utcoffset() is None:
            issues.append(
                _issue(
                    "observed_at_naive",
                    "observation timestamp must include a timezone",
                    FailureKind.SCHEMA,
                )
            )

    @staticmethod
    def _validate_price(
        product: ExtractedProduct,
        target: ScrapeTarget,
        issues: list[ValidationIssue],
    ) -> None:
        if not product.price.is_finite():
            return
        if product.price <= 0:
            issues.append(
                _issue(
                    "price_non_positive",
                    "price must be greater than zero",
                    FailureKind.PLAUSIBILITY,
                    price=str(product.price),
                )
            )
        if (
            target.minimum_valid_price is not None
            and target.maximum_valid_price is not None
            and target.minimum_valid_price > target.maximum_valid_price
        ):
            issues.append(
                _issue(
                    "invalid_price_bounds",
                    "target minimum price exceeds its maximum price",
                    FailureKind.SCHEMA,
                )
            )
        if target.minimum_valid_price is not None and product.price < target.minimum_valid_price:
            issues.append(
                _issue(
                    "price_below_minimum",
                    "price is below the configured plausible minimum",
                    FailureKind.PLAUSIBILITY,
                    price=str(product.price),
                    minimum=str(target.minimum_valid_price),
                )
            )
        if target.maximum_valid_price is not None and product.price > target.maximum_valid_price:
            issues.append(
                _issue(
                    "price_above_maximum",
                    "price is above the configured plausible maximum",
                    FailureKind.PLAUSIBILITY,
                    price=str(product.price),
                    maximum=str(target.maximum_valid_price),
                )
            )

        if target.maximum_price_change_ratio < 0:
            issues.append(
                _issue(
                    "invalid_change_ratio",
                    "maximum price change ratio cannot be negative",
                    FailureKind.SCHEMA,
                )
            )
        elif (
            target.previous_price is not None
            and target.previous_price > 0
            and target.previous_currency in {None, product.currency}
        ):
            ratio = abs(product.price - target.previous_price) / target.previous_price
            if ratio > target.maximum_price_change_ratio:
                issues.append(
                    _issue(
                        "price_change_too_large",
                        "price change exceeds the configured plausibility ratio",
                        FailureKind.PLAUSIBILITY,
                        previous_price=str(target.previous_price),
                        price=str(product.price),
                        ratio=str(ratio),
                        maximum_ratio=str(target.maximum_price_change_ratio),
                    )
                )

    def _validate_identity(
        self,
        product: ExtractedProduct,
        target: ScrapeTarget,
        issues: list[ValidationIssue],
    ) -> None:
        try:
            product_host_value = urlsplit(str(product.product_url)).hostname
            product_host = canonicalize_host(product_host_value or "")
            allowed_hosts = {canonicalize_host(host) for host in target.allowed_hosts}
        except URLPolicyError:
            product_host = ""
            allowed_hosts = set()
        if not product_host or product_host not in allowed_hosts:
            issues.append(
                _issue(
                    "product_url_host_mismatch",
                    "product URL host is not one of the target's exact allowed hosts",
                    FailureKind.IDENTITY,
                    host=product_host,
                )
            )

        if target.expected_name:
            score = _identity_score(target.expected_name, product.name)
            if score < self.minimum_name_similarity:
                issues.append(
                    _issue(
                        "product_name_mismatch",
                        "extracted product name does not match the monitored product",
                        FailureKind.IDENTITY,
                        expected=target.expected_name,
                        actual=product.name,
                        similarity=round(score, 4),
                    )
                )
        if (
            target.expected_external_id is not None
            and product.external_product_id != target.expected_external_id
        ):
            issues.append(
                _issue(
                    "external_id_mismatch",
                    "extracted external product identifier does not match",
                    FailureKind.IDENTITY,
                    expected=target.expected_external_id,
                    actual=product.external_product_id,
                )
            )
        if target.expected_currency and product.currency != target.expected_currency.upper():
            issues.append(
                _issue(
                    "currency_mismatch",
                    "extracted currency does not match the configured currency",
                    FailureKind.IDENTITY,
                    expected=target.expected_currency.upper(),
                    actual=product.currency,
                )
            )
        if target.previous_currency and product.currency != target.previous_currency.upper():
            issues.append(
                _issue(
                    "currency_changed_unexpectedly",
                    "currency changed from the previous observation",
                    FailureKind.PLAUSIBILITY,
                    previous=target.previous_currency.upper(),
                    actual=product.currency,
                )
            )

    @staticmethod
    def _validate_evidence(
        product: ExtractedProduct,
        issues: list[ValidationIssue],
    ) -> None:
        for field in ("name", "price", "currency"):
            if field not in product.evidence:
                issues.append(
                    _issue(
                        f"{field}_evidence_missing",
                        f"{field} has no extraction evidence",
                        FailureKind.EXTRACTION,
                    )
                )

        name_evidence = product.evidence.get("name")
        if name_evidence is not None:
            evidence_name = _normalized_identity(name_evidence.raw_value)
            actual_name = _normalized_identity(product.name)
            if (
                actual_name
                and actual_name not in evidence_name
                and evidence_name not in actual_name
            ):
                issues.append(
                    _issue(
                        "name_evidence_mismatch",
                        "name evidence does not support the extracted name",
                        FailureKind.EXTRACTION,
                    )
                )

        price_evidence = product.evidence.get("price")
        if price_evidence is not None:
            try:
                evidenced_price = parse_money(price_evidence.raw_value)
            except MoneyParseError:
                issues.append(
                    _issue(
                        "price_evidence_not_numeric",
                        "price evidence does not contain a parseable numeric value",
                        FailureKind.EXTRACTION,
                    )
                )
            else:
                if evidenced_price != product.price:
                    issues.append(
                        _issue(
                            "price_evidence_mismatch",
                            "price evidence does not support the extracted price",
                            FailureKind.EXTRACTION,
                            evidence_price=str(evidenced_price),
                            price=str(product.price),
                        )
                    )

        required_container_evidence = [
            product.evidence.get("name"),
            product.evidence.get("price"),
        ]
        if any(
            item is not None and not item.container_text for item in required_container_evidence
        ):
            issues.append(
                _issue(
                    "product_context_missing",
                    "required extraction evidence is not tied to a product container",
                    FailureKind.EXTRACTION,
                )
            )
        elif price_evidence and price_evidence.container_text:
            raw_price = normalize_text(price_evidence.raw_value)
            product_context = normalize_text(price_evidence.container_text)
            if raw_price and raw_price not in product_context:
                issues.append(
                    _issue(
                        "price_context_weak",
                        "price evidence is not visible in the captured product context",
                        FailureKind.EXTRACTION,
                        severity="warning",
                    )
                )


_DEFAULT_VALIDATOR = ProductValidator()


def validate_extracted_product(
    product: ExtractedProduct,
    target: ScrapeTarget,
) -> ValidationOutcome:
    """Validate a result with the production-default deterministic policy."""

    return _DEFAULT_VALIDATOR.validate(product, target)


validate_product = validate_extracted_product
