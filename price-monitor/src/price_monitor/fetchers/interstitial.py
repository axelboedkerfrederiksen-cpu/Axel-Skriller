from __future__ import annotations

import re

_MARKERS = (
    "cf-chl-",
    "challenge-platform",
    "g-recaptcha",
    "h-captcha",
    "verify you are human",
    "checking your browser",
    "attention required! | cloudflare",
)
_TITLE_PATTERN = re.compile(
    r"<title[^>]*>\s*(?:captcha|access denied|verify (?:you are )?human|just a moment)",
    re.IGNORECASE,
)


def looks_like_anti_bot_interstitial(html: str) -> bool:
    """Recognize common challenge pages without attempting to bypass them."""

    lowered = html[:500_000].casefold()
    return any(marker in lowered for marker in _MARKERS) or bool(_TITLE_PATTERN.search(lowered))
