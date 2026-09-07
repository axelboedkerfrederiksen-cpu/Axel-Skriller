from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from price_monitor.config import Settings
from price_monitor.db.models import Competitor, Customer, RepairAttempt, ScraperHealth
from price_monitor.db.session import SessionFactory, session_scope
from price_monitor.domain.enums import HealthStatus, RepairStatus
from price_monitor.domain.types import utc_now
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.errors import LeaseLostError
from price_monitor.services.repair_coordinator import RepairCoordinator


def _coordinator(
    session_factory: SessionFactory,
    tmp_path: Path,
) -> RepairCoordinator:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        artifact_root=tmp_path / "artifacts",
        adapter_runtime_root=tmp_path / "adapters",
    )
    return RepairCoordinator(
        session_factory=session_factory,
        settings=settings,
        registry=AdapterRegistry(settings.adapter_runtime_root),
    )


def _queued_repair(session_factory: SessionFactory) -> RepairAttempt:
    with session_scope(session_factory) as session:
        customer = Customer(
            name="Lease customer",
            slug="lease-customer",
            webshop_url="https://example.test",
        )
        competitor = Competitor(
            customer=customer,
            name="Lease competitor",
            base_url="https://books.toscrape.com",
            adapter_key="books_to_scrape",
            active_scraper_revision="1",
        )
        repair = RepairAttempt(
            competitor=competitor,
            failure_signature="missing-price",
            baseline_revision="1",
        )
        session.add_all(
            [
                repair,
                ScraperHealth(competitor=competitor, status=HealthStatus.REPAIR_QUEUED),
            ]
        )
        session.flush()
        repair_id = repair.id

    with session_factory() as session:
        stored = session.get(RepairAttempt, repair_id)
        assert stored is not None
        session.expunge(stored)
        return stored


def test_active_repair_lease_is_not_claimed_twice(
    session_factory: SessionFactory,
    tmp_path: Path,
) -> None:
    repair_id = _queued_repair(session_factory).id
    coordinator = _coordinator(session_factory, tmp_path)

    claim = coordinator._claim()

    assert claim is not None
    assert coordinator._claim() is None
    with session_factory() as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        assert repair.status is RepairStatus.DIAGNOSING
        assert repair.lease_token == claim.lease_token
        assert repair.lease_expires_at is not None
        assert repair.lease_expires_at > utc_now()
        assert repair.attempt_count == 1
        assert repair.competitor.health is not None
        assert repair.competitor.health.status is HealthStatus.REPAIRING


def test_expired_diagnosing_and_testing_leases_are_reclaimed(
    session_factory: SessionFactory,
    tmp_path: Path,
) -> None:
    repair_id = _queued_repair(session_factory).id
    coordinator = _coordinator(session_factory, tmp_path)
    first = coordinator._claim()
    assert first is not None

    with session_scope(session_factory) as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        repair.lease_expires_at = utc_now() - timedelta(seconds=1)

    second = coordinator._claim()
    assert second is not None
    assert second.lease_token != first.lease_token
    with pytest.raises(LeaseLostError):
        coordinator._begin_testing(first)

    coordinator._begin_testing(second)
    with session_scope(session_factory) as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        assert repair.status is RepairStatus.TESTING
        repair.lease_expires_at = utc_now() - timedelta(seconds=1)

    third = coordinator._claim()
    assert third is not None
    assert third.lease_token not in {first.lease_token, second.lease_token}
    with session_factory() as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        assert repair.status is RepairStatus.DIAGNOSING
        assert repair.lease_token == third.lease_token
        assert repair.attempt_count == 3


def test_testing_lease_renewal_and_terminal_update_require_current_owner(
    session_factory: SessionFactory,
    tmp_path: Path,
) -> None:
    repair_id = _queued_repair(session_factory).id
    coordinator = _coordinator(session_factory, tmp_path)
    claim = coordinator._claim()
    assert claim is not None
    coordinator._begin_testing(claim)

    with session_factory() as session:
        initial_expiry = session.scalars(
            select(RepairAttempt.lease_expires_at).where(RepairAttempt.id == repair_id)
        ).one()
    assert initial_expiry is not None

    coordinator._renew_lease(claim)

    with session_factory() as session:
        renewed_expiry = session.scalars(
            select(RepairAttempt.lease_expires_at).where(RepairAttempt.id == repair_id)
        ).one()
    assert renewed_expiry is not None
    assert renewed_expiry > initial_expiry

    with session_scope(session_factory) as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        repair.lease_expires_at = utc_now() - timedelta(seconds=1)

    with session_scope(session_factory) as session, pytest.raises(LeaseLostError):
        coordinator._lock_owned(
            session,
            claim,
            allowed_statuses=(RepairStatus.TESTING,),
        )

    replacement = coordinator._claim()
    assert replacement is not None

    with session_scope(session_factory) as session:
        with pytest.raises(LeaseLostError):
            coordinator._lock_owned(
                session,
                claim,
                allowed_statuses=(RepairStatus.DIAGNOSING, RepairStatus.TESTING),
            )

        current = coordinator._lock_owned(
            session,
            replacement,
            allowed_statuses=(RepairStatus.DIAGNOSING,),
        )
        result = coordinator._reject(current, reason="fixture failed")
        assert result.status is RepairStatus.REJECTED

    with session_factory() as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        assert repair.status is RepairStatus.REJECTED
        assert repair.lease_token is None
        assert repair.lease_expires_at is None


def test_heartbeat_renews_lease_during_evaluation(
    session_factory: SessionFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repair_id = _queued_repair(session_factory).id
    coordinator = _coordinator(session_factory, tmp_path)
    claim = coordinator._claim()
    assert claim is not None
    coordinator._begin_testing(claim)
    with session_factory() as session:
        initial_expiry = session.scalars(
            select(RepairAttempt.lease_expires_at).where(RepairAttempt.id == repair_id)
        ).one()
    assert initial_expiry is not None

    renewed = Event()
    renew = coordinator._renew_lease

    def renew_and_signal() -> None:
        renew(claim)
        renewed.set()

    monkeypatch.setattr(coordinator, "_heartbeat_interval_seconds", lambda: 0.01)
    monkeypatch.setattr(coordinator, "_renew_lease", lambda _claim: renew_and_signal())

    with coordinator._maintain_lease(claim):
        assert renewed.wait(timeout=1)

    with session_factory() as session:
        heartbeat_expiry = session.scalars(
            select(RepairAttempt.lease_expires_at).where(RepairAttempt.id == repair_id)
        ).one()
    assert heartbeat_expiry is not None
    assert heartbeat_expiry > initial_expiry


def test_database_rejects_processing_status_without_a_complete_lease(
    session_factory: SessionFactory,
) -> None:
    repair_id = _queued_repair(session_factory).id

    with session_factory() as session:
        repair = session.get(RepairAttempt, repair_id)
        assert repair is not None
        repair.status = RepairStatus.DIAGNOSING
        with pytest.raises(IntegrityError):
            session.commit()
