from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from price_monitor.config import Settings
from price_monitor.db.models import (
    Competitor,
    CompetitorProduct,
    PriceHistory,
    RepairAttempt,
    ScrapeResult,
    ScraperHealth,
)
from price_monitor.domain.enums import (
    ChangeKind,
    FailureKind,
    HealthStatus,
    RepairStatus,
    ResultStatus,
)
from price_monitor.domain.types import ExtractedProduct, ValidationOutcome, utc_now
from price_monitor.services.errors import LeaseLostError, NotFoundError

TERMINAL_RESULT_STATUSES = {
    ResultStatus.SUCCEEDED,
    ResultStatus.INVALID,
    ResultStatus.FAILED,
    ResultStatus.TIMED_OUT,
}
OPEN_REPAIR_STATUSES = {
    RepairStatus.QUEUED,
    RepairStatus.DIAGNOSING,
    RepairStatus.CANDIDATE_READY,
    RepairStatus.TESTING,
    RepairStatus.VALIDATED,
}
REPAIRABLE_FAILURES = tuple(kind for kind in FailureKind if kind.is_repairable)


class ResultRecorder:
    """Sole owner of terminal scrape, history, and health transactions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def record_success(
        self,
        session: Session,
        *,
        result_id: UUID,
        lease_token: UUID,
        extracted: ExtractedProduct,
        validation: ValidationOutcome,
        duration_ms: int,
        http_status: int,
        html_artifact_uri: str,
        html_sha256: str,
    ) -> tuple[ScrapeResult, PriceHistory]:
        if not validation.accepted:
            raise ValueError("record_success requires an accepted validation outcome")
        result, target = self._lock_result_and_target(session, result_id, lease_token)
        previous = session.scalar(
            select(PriceHistory)
            .where(PriceHistory.competitor_product_id == target.id)
            .order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc())
            .limit(1)
        )
        previous_price = previous.price if previous else None
        previous_currency = previous.currency if previous else None
        change_kind, amount, percentage = self._change(
            previous_price,
            previous_currency,
            extracted.price,
            extracted.currency,
        )

        result.status = ResultStatus.SUCCEEDED
        result.observed_at = extracted.observed_at
        result.finished_at = utc_now()
        result.duration_ms = duration_ms
        result.http_status = http_status
        result.observed_name = extracted.name
        result.price = extracted.price
        result.currency = extracted.currency
        result.availability = extracted.availability
        price_evidence = extracted.evidence.get("price")
        result.raw_price_text = price_evidence.raw_value if price_evidence else None
        result.previous_price = previous_price
        result.previous_currency = previous_currency
        result.is_price_change = change_kind not in {ChangeKind.INITIAL, ChangeKind.UNCHANGED}
        result.failure_kind = None
        result.failure_code = None
        result.failure_message = None
        result.validation_errors = [issue.model_dump(mode="json") for issue in validation.issues]
        result.extraction_evidence = {
            field: evidence.model_dump(mode="json")
            for field, evidence in extracted.evidence.items()
        }
        result.html_artifact_uri = html_artifact_uri
        result.html_sha256 = html_sha256
        result.lease_token = None
        result.lease_expires_at = None

        history = PriceHistory(
            competitor_product_id=target.id,
            scrape_result_id=result.id,
            observed_at=extracted.observed_at,
            price=extracted.price,
            currency=extracted.currency,
            availability=extracted.availability,
            previous_price=previous_price,
            previous_currency=previous_currency,
            change_amount=amount,
            change_percent=percentage,
            change_kind=change_kind,
        )
        session.add(history)
        target.current_price = extracted.price
        target.current_currency = extracted.currency
        target.current_availability = extracted.availability
        target.current_observed_at = extracted.observed_at
        target.last_success_at = extracted.observed_at
        target.consecutive_failures = 0
        self._mark_healthy(session, target.competitor_id, result)
        session.flush()
        return result, history

    def record_invalid(
        self,
        session: Session,
        *,
        result_id: UUID,
        lease_token: UUID,
        extracted: ExtractedProduct | None,
        validation: ValidationOutcome,
        duration_ms: int,
        http_status: int | None,
        html_artifact_uri: str | None,
        html_sha256: str | None,
        failure_code: str = "VALIDATION_FAILED",
    ) -> tuple[ScrapeResult, RepairAttempt | None]:
        kind = validation.primary_failure_kind or FailureKind.SCHEMA
        message = "; ".join(issue.message for issue in validation.issues) or "validation failed"
        result, target = self._lock_result_and_target(session, result_id, lease_token)
        if extracted is not None:
            result.observed_at = extracted.observed_at
            result.observed_name = extracted.name
            result.price = extracted.price
            result.currency = extracted.currency
            result.availability = extracted.availability
            price_evidence = extracted.evidence.get("price")
            result.raw_price_text = price_evidence.raw_value if price_evidence else None
            result.extraction_evidence = {
                field: evidence.model_dump(mode="json")
                for field, evidence in extracted.evidence.items()
            }
        result.validation_errors = [issue.model_dump(mode="json") for issue in validation.issues]
        return self._finish_failure(
            session,
            result=result,
            target=target,
            status=ResultStatus.INVALID,
            failure_kind=kind,
            failure_code=failure_code,
            message=message,
            duration_ms=duration_ms,
            http_status=http_status,
            html_artifact_uri=html_artifact_uri,
            html_sha256=html_sha256,
        )

    def record_failure(
        self,
        session: Session,
        *,
        result_id: UUID,
        lease_token: UUID,
        failure_kind: FailureKind,
        failure_code: str,
        message: str,
        duration_ms: int,
        status: ResultStatus = ResultStatus.FAILED,
        http_status: int | None = None,
        html_artifact_uri: str | None = None,
        html_sha256: str | None = None,
    ) -> tuple[ScrapeResult, RepairAttempt | None]:
        if status not in {ResultStatus.FAILED, ResultStatus.TIMED_OUT, ResultStatus.INVALID}:
            raise ValueError("failure status must be terminal and unsuccessful")
        result, target = self._lock_result_and_target(session, result_id, lease_token)
        return self._finish_failure(
            session,
            result=result,
            target=target,
            status=status,
            failure_kind=failure_kind,
            failure_code=failure_code,
            message=message,
            duration_ms=duration_ms,
            http_status=http_status,
            html_artifact_uri=html_artifact_uri,
            html_sha256=html_sha256,
        )

    def _finish_failure(
        self,
        session: Session,
        *,
        result: ScrapeResult,
        target: CompetitorProduct,
        status: ResultStatus,
        failure_kind: FailureKind,
        failure_code: str,
        message: str,
        duration_ms: int,
        http_status: int | None,
        html_artifact_uri: str | None,
        html_sha256: str | None,
    ) -> tuple[ScrapeResult, RepairAttempt | None]:
        finished_at = utc_now()
        result.status = status
        result.finished_at = finished_at
        result.duration_ms = max(0, duration_ms)
        result.http_status = http_status
        result.failure_kind = failure_kind
        result.failure_code = failure_code[:100]
        result.failure_message = message[:10_000]
        result.html_artifact_uri = html_artifact_uri
        result.html_sha256 = html_sha256
        result.lease_token = None
        result.lease_expires_at = None
        target.consecutive_failures += 1
        health = self._health(session, target.competitor_id)
        health.last_attempt_at = finished_at
        health.last_failure_at = finished_at
        health.last_failure_kind = failure_kind
        health.last_failure_message = message[:10_000]
        health.last_scrape_result_id = result.id
        health.recent_failure_count += 1
        if failure_kind.is_repairable:
            health.consecutive_repairable_failures += 1
        else:
            health.consecutive_repairable_failures = 0
        health.status = HealthStatus.DEGRADED
        session.flush()

        repair = self._maybe_create_repair(session, result, target, health)
        session.flush()
        return result, repair

    def _maybe_create_repair(
        self,
        session: Session,
        result: ScrapeResult,
        target: CompetitorProduct,
        health: ScraperHealth,
    ) -> RepairAttempt | None:
        if (
            result.failure_kind is None
            or not result.failure_kind.is_repairable
            or health.consecutive_repairable_failures < self.settings.repair_failure_threshold
        ):
            return None

        competitor = session.get(Competitor, target.competitor_id)
        assert competitor is not None
        total_targets = (
            session.scalar(
                select(func.count(CompetitorProduct.id)).where(
                    CompetitorProduct.competitor_id == competitor.id,
                    CompetitorProduct.is_active.is_(True),
                )
            )
            or 0
        )
        required_distinct = min(self.settings.repair_minimum_distinct_targets, total_targets)
        since = utc_now() - timedelta(hours=24)
        distinct_targets = (
            session.scalar(
                select(func.count(distinct(ScrapeResult.competitor_product_id)))
                .join(
                    CompetitorProduct,
                    ScrapeResult.competitor_product_id == CompetitorProduct.id,
                )
                .where(
                    CompetitorProduct.competitor_id == competitor.id,
                    ScrapeResult.failure_kind.in_(REPAIRABLE_FAILURES),
                    ScrapeResult.finished_at >= since,
                )
            )
            or 0
        )
        if distinct_targets < required_distinct:
            health.status = HealthStatus.BROKEN
            return None

        open_repair = session.scalar(
            select(RepairAttempt).where(
                RepairAttempt.competitor_id == competitor.id,
                RepairAttempt.status.in_(OPEN_REPAIR_STATUSES),
            )
        )
        if open_repair is not None:
            health.status = HealthStatus.REPAIR_QUEUED
            return open_repair

        cooldown_since = utc_now() - timedelta(seconds=self.settings.repair_cooldown_seconds)
        recent_closed = session.scalar(
            select(RepairAttempt.id)
            .where(
                RepairAttempt.competitor_id == competitor.id,
                RepairAttempt.finished_at >= cooldown_since,
            )
            .limit(1)
        )
        if recent_closed is not None:
            health.status = HealthStatus.BROKEN
            return None

        signature_input = ":".join(
            (
                competitor.adapter_key,
                result.scraper_revision,
                result.failure_kind.value,
                result.failure_code or "UNKNOWN",
            )
        )
        signature = hashlib.sha256(signature_input.encode()).hexdigest()
        repair = RepairAttempt(
            competitor_id=competitor.id,
            trigger_scrape_result_id=result.id,
            status=RepairStatus.QUEUED,
            failure_signature=signature,
            diagnostic_artifact_uri=result.html_artifact_uri,
            baseline_revision=result.scraper_revision,
        )
        try:
            with session.begin_nested():
                session.add(repair)
                session.flush()
        except IntegrityError:
            # A second worker may cross the threshold concurrently. The database's
            # partial unique index is authoritative; reuse the winner's task.
            concurrent = session.scalar(
                select(RepairAttempt).where(
                    RepairAttempt.competitor_id == competitor.id,
                    RepairAttempt.status.in_(OPEN_REPAIR_STATUSES),
                )
            )
            if concurrent is None:
                raise
            repair = concurrent
        health.status = HealthStatus.REPAIR_QUEUED
        return repair

    def _lock_result_and_target(
        self, session: Session, result_id: UUID, lease_token: UUID
    ) -> tuple[ScrapeResult, CompetitorProduct]:
        result = session.scalar(
            select(ScrapeResult).where(ScrapeResult.id == result_id).with_for_update()
        )
        if result is None:
            raise NotFoundError(f"ScrapeResult {result_id} was not found")
        if result.status in TERMINAL_RESULT_STATUSES:
            raise LeaseLostError("scrape result is already finalized")
        if result.status != ResultStatus.RUNNING or result.lease_token != lease_token:
            raise LeaseLostError("scrape worker no longer owns this lease")
        if result.lease_expires_at is None or result.lease_expires_at <= utc_now():
            raise LeaseLostError("scrape worker lease has expired")
        target = session.scalar(
            select(CompetitorProduct)
            .where(CompetitorProduct.id == result.competitor_product_id)
            .with_for_update()
        )
        assert target is not None
        return result, target

    def _health(self, session: Session, competitor_id: UUID) -> ScraperHealth:
        health = session.get(ScraperHealth, competitor_id)
        if health is None:
            health = ScraperHealth(competitor_id=competitor_id)
            session.add(health)
            session.flush()
        return health

    def _mark_healthy(
        self, session: Session, competitor_id: UUID, result: ScrapeResult
    ) -> ScraperHealth:
        health = self._health(session, competitor_id)
        health.status = HealthStatus.HEALTHY
        health.consecutive_repairable_failures = 0
        health.recent_failure_count = 0
        health.last_attempt_at = result.finished_at
        health.last_success_at = result.observed_at
        health.last_scrape_result_id = result.id
        return health

    @staticmethod
    def _change(
        previous_price: Decimal | None,
        previous_currency: str | None,
        price: Decimal,
        currency: str,
    ) -> tuple[ChangeKind, Decimal | None, Decimal | None]:
        if previous_price is None or previous_currency is None:
            return ChangeKind.INITIAL, None, None
        if previous_currency != currency:
            return ChangeKind.CURRENCY_CHANGED, None, None
        amount = price - previous_price
        if amount == 0:
            return ChangeKind.UNCHANGED, Decimal("0"), Decimal("0")
        percentage = (amount / previous_price * Decimal("100")).quantize(Decimal("0.000001"))
        kind = ChangeKind.INCREASE if amount > 0 else ChangeKind.DECREASE
        return kind, amount, percentage
