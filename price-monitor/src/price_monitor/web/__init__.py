from __future__ import annotations

from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent


def read_index_html() -> str:
    """Return the operational UI shell bundled with the application."""

    return (WEB_ROOT / "index.html").read_text(encoding="utf-8")


__all__ = ["WEB_ROOT", "read_index_html"]
