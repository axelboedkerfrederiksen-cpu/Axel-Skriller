from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.domain.enums import FetchMode
from price_monitor.domain.types import ScrapeTarget, utc_now
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.errors import LeaseLostError
from price_monitor.services.queue import ClaimedScrape
from price_monitor.services.worker import ScrapeWorker


class _BlockingWorker(ScrapeWorker):
    cancelled = False
    reached_finalization = False

    async def _process(self, claimed: ClaimedScrape) -> None:
        del claimed
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        self.reached_finalization = True


def _claimed(*, lease_seconds: float = 30) -> ClaimedScrape:
    return ClaimedScrape(
        result_id=uuid4(),
        lease_token=uuid4(),
        lease_expires_at=utc_now() + timedelta(seconds=lease_seconds),
        competitor_id=uuid4(),
        target=ScrapeTarget(
            competitor_product_id=str(uuid4()),
            url="https://books.toscrape.com/catalogue/example/index.html",
            allowed_hosts=("books.toscrape.com",),
            adapter_key="books_to_scrape",
            adapter_revision="1",
            fetch_mode=FetchMode.HTTP,
        ),
        timeout_seconds=120,
        maximum_retries=5,
        minimum_request_interval_ms=1_000,
    )


def _worker(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> _BlockingWorker:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
        worker_lease_seconds=30,
    )
    return _BlockingWorker(
        session_factory=session_factory,
        settings=settings,
        registry=AdapterRegistry(settings.adapter_runtime_root),
    )


def test_heartbeat_loss_cancels_work_before_finalization_in_a_separate_session(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _worker(session_factory, tmp_path)
    claimed = _claimed()
    claim_session: Session | None = None
    renewal_session: Session | None = None

    def claim_next(session: Session) -> ClaimedScrape:
        nonlocal claim_session
        claim_session = session
        return claimed

    def lose_lease(
        session: Session,
        *,
        result_id: object,
        lease_token: object,
    ) -> None:
        nonlocal renewal_session
        del result_id, lease_token
        renewal_session = session
        return None

    monkeypatch.setattr(worker.queue, "claim_next", claim_next)
    monkeypatch.setattr(worker.queue, "renew_lease", lose_lease)
    monkeypatch.setattr(worker, "_lease_renewal_interval_seconds", lambda: 0.001)

    assert asyncio.run(worker.process_one()) is True
    assert worker.cancelled is True
    assert worker.reached_finalization is False
    assert claim_session is not None
    assert renewal_session is not None
    assert renewal_session is not claim_session


def test_watchdog_cancels_work_before_database_lease_expiry(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _worker(session_factory, tmp_path)
    claimed = _claimed()

    monkeypatch.setattr(worker, "_lease_renewal_interval_seconds", lambda: 60.0)
    monkeypatch.setattr(
        worker,
        "_lease_watchdog_deadline",
        lambda expires_at: asyncio.get_running_loop().time() + 0.01,
    )

    async def scenario() -> None:
        with pytest.raises(LeaseLostError, match="deadline elapsed"):
            await worker._process_with_renewing_lease(claimed)

    asyncio.run(scenario())
    assert worker.cancelled is True
    assert worker.reached_finalization is False
