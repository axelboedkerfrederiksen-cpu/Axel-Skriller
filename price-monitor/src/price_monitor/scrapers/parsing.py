from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from price_monitor.domain.enums import Availability


class MoneyParseError(ValueError):
    """Raised when text cannot be deterministically interpreted as money."""


_NUMBER_CANDIDATE = re.compile(
    r"(?<![\w])[-+]?\s*(?:\d(?:[\d\s\u00a0\u202f'\u2019.,]*\d)?)(?![\w])"
)
_ISO_CURRENCY = re.compile(r"(?<![A-Za-z])([A-Za-z]{3})(?![A-Za-z])")


def normalize_text(value: str) -> str:
    """Collapse browser-visible whitespace after Unicode normalization."""

    return " ".join(unicodedata.normalize("NFKC", html.unescape(value)).split())


def apply_pattern(value: str, pattern: str | None) -> str | None:
    """Apply a selector rule's bounded regex with predictable group semantics."""

    if pattern is None:
        return value
    match = re.search(pattern, value)
    if match is None:
        return None
    if "value" in match.re.groupindex:
        return match.group("value")
    if match.lastindex:
        for group in match.groups():
            if group is not None:
                return group
    return match.group(0)


def _separator_roles(number: str) -> tuple[str | None, set[str]]:
    comma_positions = [index for index, char in enumerate(number) if char == ","]
    dot_positions = [index for index, char in enumerate(number) if char == "."]
    if comma_positions and dot_positions:
        decimal_separator = "," if comma_positions[-1] > dot_positions[-1] else "."
        return decimal_separator, {",", "."} - {decimal_separator}

    positions = comma_positions or dot_positions
    if not positions:
        return None, set()
    separator = "," if comma_positions else "."
    groups = number.split(separator)
    if any(not group for group in groups):
        raise MoneyParseError("malformed numeric separators")

    if len(groups) > 2:
        # 1.234.567 is grouped; 1.234.56 uses the final mark as decimal.
        if all(len(group) == 3 for group in groups[1:]):
            return None, {separator}
        if len(groups[-1]) in {1, 2} and all(len(group) == 3 for group in groups[1:-1]):
            return separator, set()
        raise MoneyParseError("ambiguous numeric separators")

    fractional_digits = len(groups[-1])
    if fractional_digits in {1, 2}:
        return separator, set()
    if fractional_digits == 3:
        return None, {separator}
    raise MoneyParseError("ambiguous decimal precision")


def parse_money(value: str) -> Decimal:
    """Parse common locale money formats without floating-point conversion.

    Supported examples include ``1,234.56``, ``1.234,56``, ``1 234,56`` and
    ``1'234.50``. A lone separator followed by three digits is treated as a
    grouping mark, matching ordinary retail-price notation.
    """

    normalized = normalize_text(value).replace("\N{MINUS SIGN}", "-")
    match = _NUMBER_CANDIDATE.search(normalized)
    if match is None:
        raise MoneyParseError("price does not contain a numeric value")
    number = match.group(0).strip().replace(" ", "")
    number = number.replace("\u00a0", "").replace("\u202f", "")
    number = number.replace("'", "").replace("\u2019", "")

    decimal_separator, grouping_separators = _separator_roles(number.lstrip("+-"))
    for separator in grouping_separators:
        number = number.replace(separator, "")
    if decimal_separator is not None:
        # Any earlier occurrences of the decimal mark are grouping marks.
        integer, fraction = number.rsplit(decimal_separator, maxsplit=1)
        integer = integer.replace(decimal_separator, "")
        number = f"{integer}.{fraction}"
    elif "," in number or "." in number:
        number = number.replace(",", "").replace(".", "")

    try:
        parsed = Decimal(number)
    except InvalidOperation as exc:
        raise MoneyParseError("price is not a valid decimal") from exc
    if not parsed.is_finite():
        raise MoneyParseError("price must be finite")
    return parsed


def detect_currency(value: str, symbol_map: Mapping[str, str] | None = None) -> str | None:
    """Extract an ISO code or a site-owned symbol mapping from visible text."""

    normalized = normalize_text(value)
    for match in _ISO_CURRENCY.finditer(normalized):
        code = match.group(1).upper()
        # Avoid interpreting ordinary three-letter words (for example "tax")
        # as currency unless the source presented them in uppercase.
        if match.group(1).isupper():
            return code
    mapping = symbol_map or {"£": "GBP", "$": "USD", "€": "EUR"}
    for symbol in sorted(mapping, key=len, reverse=True):
        if symbol and symbol in normalized:
            return mapping[symbol].upper()
    return None


def parse_availability(
    value: str,
    *,
    in_stock_terms: Sequence[str] = ("in stock", "available"),
    out_of_stock_terms: Sequence[str] = ("out of stock", "unavailable", "sold out"),
    preorder_terms: Sequence[str] = ("pre-order", "preorder"),
) -> Availability:
    """Map site-owned stock phrases to the canonical availability enum."""

    normalized = normalize_text(value).casefold()
    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    out_terms = (*out_of_stock_terms, "not available", "currently unavailable", "outofstock")
    if any(normalize_text(term).casefold() in normalized for term in out_terms) or (
        "outofstock" in compact
    ):
        return Availability.OUT_OF_STOCK
    if re.search(r"\b0\s+(?:items?\s+)?(?:in stock|available)\b", normalized):
        return Availability.OUT_OF_STOCK
    if any(normalize_text(term).casefold() in normalized for term in preorder_terms) or (
        "preorder" in compact
    ):
        return Availability.PREORDER
    if any(normalize_text(term).casefold() in normalized for term in in_stock_terms) or (
        "instock" in compact
    ):
        return Availability.IN_STOCK
    return Availability.UNKNOWN
