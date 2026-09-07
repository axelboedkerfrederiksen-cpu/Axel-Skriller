"""Vercel-compatible ASGI entrypoint for the src-layout application package."""

from price_monitor.main import app

__all__ = ["app"]
