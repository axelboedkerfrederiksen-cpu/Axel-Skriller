from __future__ import annotations

from dataclasses import dataclass

from price_monitor.repair.providers import RepairProposal, RepairProvider, RepairRequest
from price_monitor.repair.reviewer import (
    RepairFixture,
    RepairReviewReport,
    TrustedRepairReviewer,
)
from price_monitor.repair.versions import (
    ActivationResult,
    SpecVersion,
    SpecVersionError,
    SpecVersionStore,
    StaleCandidateError,
)


class UnvalidatedRepairError(SpecVersionError):
    pass


@dataclass(frozen=True, slots=True)
class RepairEvaluation:
    baseline_revision: str
    proposal: RepairProposal | None
    review: RepairReviewReport | None
    staged: SpecVersion | None

    @property
    def deployment_ready(self) -> bool:
        return (
            self.proposal is not None
            and self.review is not None
            and self.review.accepted
            and self.staged is not None
        )


class GuardedRepairWorkflow:
    """Connects proposal, deterministic review, staging, and explicit promotion."""

    def __init__(
        self,
        *,
        provider: RepairProvider,
        reviewer: TrustedRepairReviewer,
        versions: SpecVersionStore,
    ) -> None:
        self._provider = provider
        self._reviewer = reviewer
        self._versions = versions

    def evaluate(
        self,
        request: RepairRequest,
        *,
        fixtures: tuple[RepairFixture, ...],
    ) -> RepairEvaluation:
        active = self._versions.get_active(request.baseline.key)
        if active.spec != request.baseline:
            raise StaleCandidateError(
                "repair request baseline is not the currently active SiteSpec"
            )

        proposal = self._provider.propose(request)
        if proposal is None:
            return RepairEvaluation(
                baseline_revision=request.baseline.revision,
                proposal=None,
                review=None,
                staged=None,
            )

        report = self._reviewer.review(
            baseline=request.baseline,
            candidate=proposal.candidate,
            fixtures=fixtures,
            permitted_selector_fields=frozenset(request.failed_fields),
        )
        staged = None
        if report.accepted:
            staged = self._versions.stage_candidate(
                proposal.candidate,
                expected_base_revision=request.baseline.revision,
            )
        return RepairEvaluation(
            baseline_revision=request.baseline.revision,
            proposal=proposal,
            review=report,
            staged=staged,
        )

    def deploy(self, evaluation: RepairEvaluation) -> ActivationResult:
        if not evaluation.deployment_ready:
            raise UnvalidatedRepairError(
                "only a candidate accepted by the trusted reviewer may be deployed"
            )
        assert evaluation.proposal is not None
        assert evaluation.staged is not None
        staged = self._versions.get_staged(
            evaluation.proposal.candidate.key,
            evaluation.proposal.candidate.revision,
        )
        if (
            staged.sha256 != evaluation.staged.sha256
            or staged.spec != evaluation.proposal.candidate
        ):
            raise UnvalidatedRepairError("staged candidate differs from the reviewed candidate")
        return self._versions.activate(
            staged.spec.key,
            staged.spec.revision,
            expected_active_revision=evaluation.baseline_revision,
        )

    def rollback(self, key: str, *, expected_active_revision: str) -> ActivationResult:
        return self._versions.rollback(key, expected_active_revision=expected_active_revision)
