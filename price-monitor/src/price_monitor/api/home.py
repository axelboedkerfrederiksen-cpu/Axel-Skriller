from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi.responses import HTMLResponse

_WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


@lru_cache(maxsize=1)
def _workspace_html() -> str:
    return (_WEB_ROOT / "index.html").read_text(encoding="utf-8")


def homepage_response() -> HTMLResponse:
    return HTMLResponse(
        _workspace_html(),
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
    )


__all__ = ["homepage_response"]
