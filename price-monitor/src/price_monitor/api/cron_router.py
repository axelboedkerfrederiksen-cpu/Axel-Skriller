from __future__ import annotations

import hmac
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from price_monitor.config import Settings
from price_monitor.db import SessionFactory, session_scope
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.queue import ScrapeQueue
from price_monitor.services.worker import ScrapeWorker

router = APIRouter(prefix="/api/cron", tags=["automation"])


def _require_cron_secret(request: Request, settings: Settings) -> None:
    configured = settings.cron_secret
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {configured.get_secret_value()}" if configured is not None else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid cron token required",
        )


@router.get("/monitor")
async def run_monitor(request: Request) -> dict[str, int | str]:
    """Queue due targets and process a bounded batch in one Vercel invocation."""

    settings = cast(Settings, request.app.state.settings)
    _require_cron_secret(request, settings)
    session_factory = cast(SessionFactory, request.app.state.session_factory)
    registry = cast(AdapterRegistry, request.app.state.adapter_registry)

    with session_scope(session_factory) as session:
        queued = ScrapeQueue(lease_seconds=settings.worker_lease_seconds).enqueue_due(
            session,
            limit=settings.cron_max_scrapes,
        )

    worker = ScrapeWorker(
        session_factory=session_factory,
        settings=settings,
        registry=registry,
    )
    processed = 0
    try:
        for _ in range(settings.cron_max_scrapes):
            if not await worker.process_one():
                break
            processed += 1
    finally:
        await worker.aclose()

    return {"status": "ok", "queued": len(queued), "processed": processed}
