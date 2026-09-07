from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from price_monitor.db.models import Competitor, CompetitorProduct, Product, ScrapeResult
from price_monitor.domain.enums import ResultStatus
from price_monitor.domain.types import ScrapeTarget, utc_now
from price_monitor.services.errors import InvalidRequestError, NotFoundError


@dataclass(frozen=True, slots=True)
class ClaimedScrape:
    result_id: UUID
    lease_token: UUID
    lease_expires_at: datetime
    competitor_id: UUID
    target: ScrapeTarget
    timeout_seconds: int
    maximum_retries: int
    minimum_request_interval_ms: int


class ScrapeQueue:
    """PostgreSQL-backed scheduler queue with leases and SQLite test compatibility."""

    def __init__(self, *, lease_seconds: int = 300) -> None:
        self.lease_seconds = lease_seconds

    def enqueue_target(
        self,
        session: Session,
        target_id: UUID,
        *,
        run_key: str | None = None,
    ) -> ScrapeResult:
        target = session.scalar(
            select(CompetitorProduct)
            .options(
                joinedload(CompetitorProduct.competitor),
                joinedload(CompetitorProduct.product),
            )
            .where(CompetitorProduct.id == target_id)
        )
        if target is None:
            raise NotFoundError(f"CompetitorProduct {target_id} was not found")
        if not target.is_active or not target.competitor.is_active or not target.product.is_active:
            raise InvalidRequestError("inactive targets cannot be queued")

        existing = session.scalar(
            select(ScrapeResult).where(
                ScrapeResult.competitor_product_id == target_id,
                ScrapeResult.status.in_((ResultStatus.QUEUED, ResultStatus.RUNNING)),
            )
        )
        if existing is not None:
            return existing

        result = ScrapeResult(
            run_key=run_key or str(uuid4()),
            competitor_product_id=target.id,
            status=ResultStatus.QUEUED,
            scraper_revision=target.competitor.active_scraper_revision,
            fetch_mode=target.competitor.fetch_mode,
        )
        try:
            with session.begin_nested():
                session.add(result)
                session.flush()
        except IntegrityError:
            # Another scheduler may have won the partial-unique-index race.
            concurrent = session.scalar(
                select(ScrapeResult).where(
                    ScrapeResult.competitor_product_id == target_id,
                    ScrapeResult.status.in_((ResultStatus.QUEUED, ResultStatus.RUNNING)),
                )
            )
            if concurrent is None:
                raise
            return concurrent
        return result

    def enqueue_due(self, session: Session, *, limit: int = 100) -> list[ScrapeResult]:
        now = utc_now()
        statement = (
            select(CompetitorProduct)
            .join(Competitor, Competitor.id == CompetitorProduct.competitor_id)
            .join(Product, Product.id == CompetitorProduct.product_id)
            .where(
                CompetitorProduct.is_active.is_(True),
                Competitor.is_active.is_(True),
                Product.is_active.is_(True),
                CompetitorProduct.next_scrape_at <= now,
            )
            .order_by(CompetitorProduct.next_scrape_at, CompetitorProduct.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        targets = list(session.scalars(statement))
        queued: list[ScrapeResult] = []
        for target in targets:
            queued.append(self.enqueue_target(session, target.id))
            interval = (
                target.schedule_interval_seconds or target.competitor.schedule_interval_seconds
            )
            target.next_scrape_at = now + timedelta(seconds=interval)
        session.flush()
        return queued

    def claim_next(self, session: Session) -> ClaimedScrape | None:
        now = utc_now()
        result = session.scalar(
            select(ScrapeResult)
            .options(
                joinedload(ScrapeResult.competitor_product).joinedload(
                    CompetitorProduct.competitor
                ),
                joinedload(ScrapeResult.competitor_product).joinedload(CompetitorProduct.product),
            )
            .where(
                or_(
                    ScrapeResult.status == ResultStatus.QUEUED,
                    (
                        (ScrapeResult.status == ResultStatus.RUNNING)
                        & (ScrapeResult.lease_expires_at < now)
                    ),
                )
            )
            .order_by(ScrapeResult.queued_at, ScrapeResult.id)
            .limit(1)
            # Lock only the queue row. The eager-loaded relationships use
            # LEFT OUTER JOINs, which PostgreSQL cannot lock as part of FOR
            # UPDATE when some related rows may be nullable.
            .with_for_update(skip_locked=True, of=ScrapeResult)
        )
        if result is None:
            return None

        target = result.competitor_product
        competitor = target.competitor
        host = urlsplit(competitor.base_url).hostname
        if not host:
            raise InvalidRequestError("competitor base URL has no hostname")

        lease_token = uuid4()
        result.status = ResultStatus.RUNNING
        result.started_at = now
        result.lease_token = lease_token
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        result.lease_expires_at = lease_expires_at
        result.attempt_count += 1
        target.last_attempt_at = now
        session.flush()

        scrape_target = ScrapeTarget(
            competitor_product_id=str(target.id),
            url=target.product_url,
            allowed_hosts=(host.lower().rstrip("."),),
            adapter_key=competitor.adapter_key,
            adapter_revision=result.scraper_revision,
            fetch_mode=result.fetch_mode,
            expected_name=target.expected_name or target.product.name,
            expected_external_id=target.external_product_id,
            expected_currency=target.expected_currency or competitor.expected_currency,
            minimum_valid_price=target.minimum_valid_price,
            maximum_valid_price=target.maximum_valid_price,
            previous_price=target.current_price,
            previous_currency=target.current_currency,
        )
        return ClaimedScrape(
            result_id=result.id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            competitor_id=competitor.id,
            target=scrape_target,
            timeout_seconds=competitor.timeout_seconds,
            maximum_retries=competitor.max_retries,
            minimum_request_interval_ms=competitor.min_request_interval_ms,
        )

    def renew_lease(
        self,
        session: Session,
        *,
        result_id: UUID,
        lease_token: UUID,
    ) -> datetime | None:
        """Extend a live lease while refusing stale or already-expired owners.

        Locking the row makes renewal mutually exclusive with expired-job reclaim.
        The expiration predicate is deliberately checked while holding that lock:
        possession of an old token does not let a delayed worker resurrect a lease.
        """

        now = utc_now()
        result = session.scalar(
            select(ScrapeResult)
            .where(
                ScrapeResult.id == result_id,
                ScrapeResult.status == ResultStatus.RUNNING,
                ScrapeResult.lease_token == lease_token,
                ScrapeResult.lease_expires_at > now,
            )
            .with_for_update()
        )
        if result is None:
            return None

        lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        result.lease_expires_at = lease_expires_at
        session.flush()
        return lease_expires_at
