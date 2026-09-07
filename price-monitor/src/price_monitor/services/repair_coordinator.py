from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from threading import Event, Thread
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from price_monitor.config import Settings
from price_monitor.db.models import (
    Competitor,
    CompetitorProduct,
    RepairAttempt,
    ScrapeResult,
    ScraperHealth,
)
from price_monitor.db.session import SessionFactory, session_scope
from price_monitor.domain.enums import HealthStatus, RepairStatus, ResultStatus
from price_monitor.domain.types import FetchedPage, ScrapeTarget, utc_now
from price_monitor.repair import (
    DeterministicSelectorProposalProvider,
    DevelopmentSubprocessSpecRunner,
    DisabledRepairProvider,
    DockerRunnerCommand,
    DockerSpecRunner,
    GuardedRepairWorkflow,
    OpenAISelectorProposalProvider,
    RepairFixture,
    RepairProvider,
    RepairRequest,
    RepairReviewReport,
    SpecRunner,
    TrustedRepairReviewer,
)
from price_monitor.repair.versions import SpecVersionError
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.artifacts import LocalArtifactStore
from price_monitor.services.errors import ConflictError, LeaseLostError, NotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RepairProcessingResult:
    repair_id: UUID
    status: RepairStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _RepairBundle:
    repair_id: UUID
    competitor_id: UUID
    baseline_revision: str
    request: RepairRequest
    fixtures: tuple[RepairFixture, ...]


@dataclass(frozen=True, slots=True)
class _ClaimedRepair:
    repair_id: UUID
    lease_token: UUID


class RepairCoordinator:
    """Consumes durable repair tasks through the guarded declarative workflow.

    Evaluation stages a candidate but never deploys it automatically. Deployment is
    a separate explicit operation behind an operator-controlled CLI boundary.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        settings: Settings,
        registry: AdapterRegistry,
        artifacts: LocalArtifactStore | None = None,
        provider: RepairProvider | None = None,
        runner: SpecRunner | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.registry = registry
        self.artifacts = artifacts or LocalArtifactStore(settings.artifact_root)
        self.provider = provider or self._default_provider(settings)
        self.runner = runner
        self.lease_seconds = settings.worker_lease_seconds

    def evaluate_one(self) -> RepairProcessingResult | None:
        claim = self._claim()
        if claim is None:
            return None
        try:
            bundle = self._build_bundle(claim)
            baseline = self.registry.spec_at(bundle.request.baseline.key, bundle.baseline_revision)
            self._begin_testing(claim)
            workflow = GuardedRepairWorkflow(
                provider=self.provider,
                reviewer=TrustedRepairReviewer(self.runner or self._default_runner(self.settings)),
                versions=self.registry.version_store,
            )
            with self._maintain_lease(claim):
                evaluation = workflow.evaluate(bundle.request, fixtures=bundle.fixtures)
            with session_scope(self.session_factory) as session:
                repair = self._lock_owned(
                    session,
                    claim,
                    allowed_statuses=(RepairStatus.TESTING,),
                )
                if evaluation.proposal is None:
                    return self._reject(
                        repair,
                        reason="repair provider produced no scoped candidate",
                        failed=True,
                    )

                repair.candidate_revision = evaluation.proposal.candidate.revision
                repair.changed_files = [f"scrapers/specs/{baseline.key}.json"]
                repair.test_report = self._review_report(evaluation.review)
                repair.validation_report = self._policy_report(evaluation.review)
                if not evaluation.deployment_ready or evaluation.staged is None:
                    return self._reject(
                        repair,
                        reason="candidate failed deterministic policy or fixture validation",
                    )

                repair.status = RepairStatus.VALIDATED
                repair.patch_uri = evaluation.staged.relative_path
                repair.patch_sha256 = evaluation.staged.sha256
                repair.reviewer_decision = "accepted"
                repair.validated_at = utc_now()
                self._clear_lease(repair)
                health = session.get(ScraperHealth, bundle.competitor_id)
                if health is not None:
                    health.status = HealthStatus.REPAIRING
                return RepairProcessingResult(repair.id, repair.status)
        except LeaseLostError:
            logger.warning("repair worker no longer owns lease for %s", claim.repair_id)
            raise
        except Exception as exc:
            logger.exception("repair evaluation failed for %s", claim.repair_id)
            with session_scope(self.session_factory) as session:
                repair = self._lock_owned(
                    session,
                    claim,
                    allowed_statuses=(
                        RepairStatus.DIAGNOSING,
                        RepairStatus.CANDIDATE_READY,
                        RepairStatus.TESTING,
                    ),
                )
                return self._reject(
                    repair,
                    reason=f"{type(exc).__name__}: {exc}",
                    failed=True,
                )

    def deploy(self, repair_id: UUID) -> RepairProcessingResult:
        with self.session_factory() as session:
            repair = session.get(RepairAttempt, repair_id)
            if repair is None:
                raise NotFoundError(f"RepairAttempt {repair_id} was not found")
            competitor = session.get(Competitor, repair.competitor_id)
            assert competitor is not None
            if repair.status != RepairStatus.VALIDATED:
                raise ConflictError("only a validated repair can be deployed")
            if not repair.candidate_revision or not repair.patch_sha256:
                raise ConflictError("validated repair is missing its staged candidate")
            staged = self.registry.version_store.get_staged(
                competitor.adapter_key, repair.candidate_revision
            )
            if staged.sha256 != repair.patch_sha256:
                raise ConflictError("staged repair digest does not match the reviewed candidate")

            activation = self.registry.version_store.activate(
                competitor.adapter_key,
                repair.candidate_revision,
                expected_active_revision=repair.baseline_revision,
            )
            try:
                competitor.previous_scraper_revision = repair.baseline_revision
                competitor.active_scraper_revision = activation.active.spec.revision
                repair.status = RepairStatus.DEPLOYED
                repair.deployed_at = utc_now()
                repair.finished_at = utc_now()
                health = session.get(ScraperHealth, competitor.id)
                if health is not None:
                    # A real successful scrape, not deployment, restores HEALTHY.
                    health.status = HealthStatus.REPAIRING
                session.flush()
                session.commit()
            except Exception:
                session.rollback()
                self.registry.version_store.rollback(
                    competitor.adapter_key,
                    expected_active_revision=activation.active.spec.revision,
                )
                raise
            return RepairProcessingResult(repair.id, repair.status)

    def rollback_competitor(self, competitor_id: UUID) -> str:
        with self.session_factory() as session:
            competitor = session.get(Competitor, competitor_id)
            if competitor is None:
                raise NotFoundError(f"Competitor {competitor_id} was not found")
            current_revision = competitor.active_scraper_revision
            activation = self.registry.version_store.rollback(
                competitor.adapter_key,
                expected_active_revision=current_revision,
            )
            try:
                competitor.active_scraper_revision = activation.active.spec.revision
                competitor.previous_scraper_revision = current_revision
                latest = session.scalar(
                    select(RepairAttempt)
                    .where(
                        RepairAttempt.competitor_id == competitor.id,
                        RepairAttempt.status == RepairStatus.DEPLOYED,
                    )
                    .order_by(RepairAttempt.deployed_at.desc(), RepairAttempt.id.desc())
                    .limit(1)
                )
                if latest is not None:
                    latest.status = RepairStatus.ROLLED_BACK
                    latest.rolled_back_at = utc_now()
                health = session.get(ScraperHealth, competitor.id)
                if health is not None:
                    health.status = HealthStatus.DEGRADED
                session.flush()
                session.commit()
                return activation.active.spec.revision
            except Exception:
                session.rollback()
                self.registry.version_store.rollback(
                    competitor.adapter_key,
                    expected_active_revision=activation.active.spec.revision,
                )
                raise

    def _claim(self) -> _ClaimedRepair | None:
        with session_scope(self.session_factory) as session:
            now = utc_now()
            repair = session.scalar(
                select(RepairAttempt)
                .where(
                    or_(
                        RepairAttempt.status == RepairStatus.QUEUED,
                        (
                            RepairAttempt.status.in_(
                                (
                                    RepairStatus.DIAGNOSING,
                                    RepairStatus.CANDIDATE_READY,
                                    RepairStatus.TESTING,
                                )
                            )
                            & (RepairAttempt.lease_expires_at < now)
                        ),
                    )
                )
                .order_by(RepairAttempt.queued_at, RepairAttempt.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if repair is None:
                return None
            lease_token = uuid4()
            repair.status = RepairStatus.DIAGNOSING
            repair.started_at = repair.started_at or now
            repair.candidate_ready_at = None
            repair.testing_started_at = None
            repair.validated_at = None
            repair.finished_at = None
            repair.candidate_revision = None
            repair.patch_uri = None
            repair.patch_sha256 = None
            repair.changed_files = []
            repair.test_report = {}
            repair.validation_report = {}
            repair.reviewer_decision = None
            repair.rejection_reason = None
            repair.lease_token = lease_token
            repair.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            repair.attempt_count += 1
            health = session.get(ScraperHealth, repair.competitor_id)
            if health is not None:
                health.status = HealthStatus.REPAIRING
            session.flush()
            return _ClaimedRepair(repair.id, lease_token)

    def _begin_testing(self, claim: _ClaimedRepair) -> None:
        with session_scope(self.session_factory) as session:
            repair = self._lock_owned(
                session,
                claim,
                allowed_statuses=(RepairStatus.DIAGNOSING,),
            )
            now = utc_now()
            repair.status = RepairStatus.TESTING
            repair.testing_started_at = now
            repair.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            session.flush()

    @contextmanager
    def _maintain_lease(self, claim: _ClaimedRepair) -> Iterator[None]:
        """Renew ownership while provider and isolated fixture evaluation run."""

        stop = Event()
        failures: list[Exception] = []
        interval_seconds = self._heartbeat_interval_seconds()

        def heartbeat() -> None:
            while not stop.wait(interval_seconds):
                try:
                    self._renew_lease(claim)
                except Exception as exc:
                    failures.append(exc)
                    stop.set()

        thread = Thread(
            target=heartbeat,
            name=f"repair-lease-{claim.repair_id}",
            daemon=True,
        )
        thread.start()
        completed = False
        try:
            yield
            completed = True
        finally:
            stop.set()
            thread.join(timeout=min(interval_seconds, 5.0))
            if completed and thread.is_alive():
                raise LeaseLostError("repair lease heartbeat did not stop cleanly")
            if completed and failures:
                raise LeaseLostError("repair lease heartbeat failed") from failures[0]

    def _heartbeat_interval_seconds(self) -> float:
        return max(1.0, min(float(self.lease_seconds) / 3, 30.0))

    def _renew_lease(self, claim: _ClaimedRepair) -> None:
        with session_scope(self.session_factory) as session:
            repair = self._lock_owned(
                session,
                claim,
                allowed_statuses=(RepairStatus.TESTING,),
            )
            repair.lease_expires_at = utc_now() + timedelta(seconds=self.lease_seconds)
            session.flush()

    def _build_bundle(self, claim: _ClaimedRepair) -> _RepairBundle:
        with self.session_factory() as session:
            repair = session.scalar(
                select(RepairAttempt)
                .options(
                    joinedload(RepairAttempt.competitor),
                    joinedload(RepairAttempt.trigger_scrape_result)
                    .joinedload(ScrapeResult.competitor_product)
                    .joinedload(CompetitorProduct.product),
                )
                .where(
                    RepairAttempt.id == claim.repair_id,
                    RepairAttempt.status == RepairStatus.DIAGNOSING,
                    RepairAttempt.lease_token == claim.lease_token,
                    RepairAttempt.lease_expires_at > utc_now(),
                )
            )
            if repair is None:
                raise LeaseLostError("repair worker no longer owns this lease")
            trigger = repair.trigger_scrape_result
            if trigger is None or trigger.html_artifact_uri is None or trigger.html_sha256 is None:
                raise ConflictError("repair task has no verified failing HTML snapshot")
            target_model = trigger.competitor_product
            failing_html = self.artifacts.read_html(
                trigger.html_artifact_uri,
                expected_content_sha256=trigger.html_sha256,
            )
            baseline = self.registry.spec_at(
                repair.competitor.adapter_key, repair.baseline_revision
            )
            successes = list(
                session.scalars(
                    select(ScrapeResult)
                    .join(
                        CompetitorProduct,
                        ScrapeResult.competitor_product_id == CompetitorProduct.id,
                    )
                    .options(
                        joinedload(ScrapeResult.competitor_product).joinedload(
                            CompetitorProduct.product
                        ),
                        joinedload(ScrapeResult.competitor_product).joinedload(
                            CompetitorProduct.competitor
                        ),
                    )
                    .where(
                        CompetitorProduct.competitor_id == repair.competitor_id,
                        ScrapeResult.status == ResultStatus.SUCCEEDED,
                        ScrapeResult.scraper_revision == repair.baseline_revision,
                        ScrapeResult.html_artifact_uri.is_not(None),
                        ScrapeResult.html_sha256.is_not(None),
                    )
                    .order_by(ScrapeResult.finished_at.desc(), ScrapeResult.id.desc())
                    .limit(10)
                )
            )
            if len(successes) < 2:
                raise ConflictError("repair requires at least two verified known-good snapshots")
            old_html = tuple(self._read_result_html(result) for result in successes[:2])
            fixtures = (
                self._known_good_fixture("known-good", "old", successes[0], old_html[0]),
                self._new_fixture(trigger, target_model, failing_html),
                self._known_good_fixture("holdout", "holdout", successes[1], old_html[1]),
            )
            request = RepairRequest(
                baseline=baseline,
                new_html=failing_html,
                old_html_samples=tuple(sample[:2_000_000] for sample in old_html),
                failed_fields=self._failed_fields(trigger),
                failure_summary=(
                    f"{trigger.failure_code or 'UNKNOWN'}: "
                    f"{(trigger.failure_message or 'no failure message')[:1_800]}"
                ),
                validation_errors=tuple(trigger.validation_errors),
                test_manifest=tuple(
                    {
                        "name": fixture.name,
                        "cohort": fixture.cohort,
                        "expected_name": fixture.expected_name,
                        "expected_price": (
                            str(fixture.expected_price)
                            if fixture.expected_price is not None
                            else None
                        ),
                        "expected_currency": fixture.expected_currency,
                    }
                    for fixture in fixtures
                ),
            )
            return _RepairBundle(
                repair_id=repair.id,
                competitor_id=repair.competitor_id,
                baseline_revision=repair.baseline_revision,
                request=request,
                fixtures=fixtures,
            )

    def _read_result_html(self, result: ScrapeResult) -> str:
        assert result.html_artifact_uri is not None and result.html_sha256 is not None
        return self.artifacts.read_html(
            result.html_artifact_uri,
            expected_content_sha256=result.html_sha256,
        )

    def _known_good_fixture(
        self, name: str, cohort: str, result: ScrapeResult, html: str
    ) -> RepairFixture:
        target = result.competitor_product
        assert result.price is not None and result.currency is not None
        return RepairFixture(
            name=f"{name}-{result.id}",
            cohort=cohort,  # type: ignore[arg-type]
            page=self._page(result, target, html),
            target=self._target(target, result.scraper_revision),
            expected_name=result.observed_name,
            expected_price=result.price,
            expected_currency=result.currency,
            expected_availability=result.availability,
        )

    def _new_fixture(
        self, result: ScrapeResult, target: CompetitorProduct, html: str
    ) -> RepairFixture:
        return RepairFixture(
            name=f"new-failure-{result.id}",
            cohort="new",
            page=self._page(result, target, html),
            target=self._target(target, result.scraper_revision),
            expected_name=target.expected_name or target.product.name,
            expected_currency=target.expected_currency or target.competitor.expected_currency,
        )

    @staticmethod
    def _page(result: ScrapeResult, target: CompetitorProduct, html: str) -> FetchedPage:
        digest = hashlib.sha256(html.encode()).hexdigest()
        if result.html_sha256 != digest:
            raise ConflictError("stored page digest differs from scrape result")
        return FetchedPage(
            requested_url=target.product_url,
            final_url=target.product_url,
            html=html,
            status_code=result.http_status or 200,
            fetched_at=result.observed_at or result.finished_at or utc_now(),
            duration_ms=result.duration_ms or 0,
            content_sha256=digest,
        )

    @staticmethod
    def _target(target: CompetitorProduct, revision: str) -> ScrapeTarget:
        hostname = urlsplit(target.competitor.base_url).hostname
        if not hostname:
            raise ConflictError("competitor base URL has no hostname")
        return ScrapeTarget(
            competitor_product_id=str(target.id),
            url=target.product_url,
            allowed_hosts=(hostname.lower().rstrip("."),),
            adapter_key=target.competitor.adapter_key,
            adapter_revision=revision,
            fetch_mode=target.competitor.fetch_mode,
            expected_name=target.expected_name or target.product.name,
            expected_external_id=target.external_product_id,
            expected_currency=target.expected_currency or target.competitor.expected_currency,
            minimum_valid_price=target.minimum_valid_price,
            maximum_valid_price=target.maximum_valid_price,
        )

    @staticmethod
    def _failed_fields(result: ScrapeResult) -> frozenset[str]:
        validation_codes = " ".join(
            str(issue.get("code", "")) for issue in result.validation_errors
        )
        code = f"{result.failure_code or ''} {validation_codes}".casefold()
        for field in (
            "external_product_id",
            "availability",
            "currency",
            "price",
            "name",
        ):
            if field in code:
                return frozenset({field})
        return frozenset({"name", "price"})

    @staticmethod
    def _review_report(review: RepairReviewReport | None) -> dict[str, object]:
        if review is None:
            return {"accepted": False, "fixtures": []}
        return {
            "accepted": bool(review.accepted),
            "fixtures": [
                {
                    "name": fixture.fixture_name,
                    "cohort": fixture.cohort,
                    "passed": fixture.passed,
                    "failures": list(fixture.failures),
                    "runner_error": fixture.run.error_type,
                }
                for fixture in review.fixtures
            ],
        }

    @staticmethod
    def _policy_report(review: RepairReviewReport | None) -> dict[str, object]:
        if review is None:
            return {"accepted": False, "violations": []}
        policy = review.policy
        return {
            "accepted": policy.accepted,
            "changed_fields": list(policy.changed_fields),
            "violations": [
                {"code": item.code, "message": item.message, "field": item.field}
                for item in policy.violations
            ],
        }

    @staticmethod
    def _reject(
        repair: RepairAttempt, *, reason: str, failed: bool = False
    ) -> RepairProcessingResult:
        repair.status = RepairStatus.FAILED if failed else RepairStatus.REJECTED
        repair.reviewer_decision = "rejected"
        repair.rejection_reason = reason[:10_000]
        repair.finished_at = utc_now()
        RepairCoordinator._clear_lease(repair)
        if repair.competitor.health is not None:
            repair.competitor.health.status = HealthStatus.BROKEN
        return RepairProcessingResult(repair.id, repair.status, reason)

    @staticmethod
    def _lock_owned(
        session: Session,
        claim: _ClaimedRepair,
        *,
        allowed_statuses: tuple[RepairStatus, ...],
    ) -> RepairAttempt:
        repair = session.scalar(
            select(RepairAttempt)
            .where(
                RepairAttempt.id == claim.repair_id,
                RepairAttempt.status.in_(allowed_statuses),
                RepairAttempt.lease_token == claim.lease_token,
                RepairAttempt.lease_expires_at > utc_now(),
            )
            .with_for_update()
        )
        if repair is None:
            raise LeaseLostError("repair worker no longer owns this lease")
        return repair

    @staticmethod
    def _clear_lease(repair: RepairAttempt) -> None:
        repair.lease_token = None
        repair.lease_expires_at = None

    @staticmethod
    def _default_runner(settings: Settings) -> SpecRunner:
        if settings.environment.casefold() == "production":
            if not settings.repair_runner_image:
                raise SpecVersionError(
                    "production repair evaluation requires PRICE_MONITOR_REPAIR_RUNNER_IMAGE"
                )
            return DockerSpecRunner(DockerRunnerCommand(image=settings.repair_runner_image))
        return DevelopmentSubprocessSpecRunner(environment=settings.environment)

    @staticmethod
    def _default_provider(settings: Settings) -> RepairProvider:
        if settings.repair_provider == "disabled":
            return DisabledRepairProvider()
        if settings.repair_provider == "openai":
            assert settings.openai_repair_model is not None
            assert settings.openai_api_key is not None
            return OpenAISelectorProposalProvider(
                model=settings.openai_repair_model,
                api_key=settings.openai_api_key.get_secret_value(),
            )
        return DeterministicSelectorProposalProvider()
