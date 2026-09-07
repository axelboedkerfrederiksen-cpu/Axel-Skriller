from __future__ import annotations

import json
import sys
from typing import Any

from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.scrapers.selector import SelectorScraper
from price_monitor.scrapers.spec import SiteSpec
from price_monitor.services.validation import validate_extracted_product

_MAX_INPUT_BYTES = 25_000_000


def _write(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()


def main() -> None:
    encoded = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if len(encoded) > _MAX_INPUT_BYTES:
        _write(
            {
                "ok": False,
                "error_type": "InputTooLarge",
                "error_message": "runner input exceeded its size limit",
            }
        )
        return
    try:
        payload = json.loads(encoded)
        spec = SiteSpec.model_validate(payload["spec"])
        page = FetchedPage.model_validate(payload["page"])
        target = ScrapeTarget.model_validate(payload["target"])
        if target.adapter_key != spec.key or target.adapter_revision != spec.revision:
            raise ValueError("target adapter identity does not match candidate SiteSpec")
        product = SelectorScraper(spec).extract(page)
        validation = validate_extracted_product(product, target)
    except Exception as exc:
        _write(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:2_000],
            }
        )
        return
    _write(
        {
            "ok": True,
            "product": product.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
        }
    )


if __name__ == "__main__":
    main()
