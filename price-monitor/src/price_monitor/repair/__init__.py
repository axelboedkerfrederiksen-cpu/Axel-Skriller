"""Guarded, declarative scraper repair workflow."""

from price_monitor.repair.policy import (
    DeclarativeRepairPolicy,
    PolicyViolation,
    RepairPolicyReport,
    validate_repair_scope,
)
from price_monitor.repair.providers import (
    DeterministicSelectorProposalProvider,
    DisabledRepairProvider,
    ManualRepairProvider,
    OpenAISelectorProposalProvider,
    RepairProposal,
    RepairProvider,
    RepairRequest,
    SelectorAddition,
    StructuredSelectorRepair,
)
from price_monitor.repair.reviewer import (
    FixtureReview,
    RepairFixture,
    RepairReviewReport,
    TrustedRepairReviewer,
)
from price_monitor.repair.runner import (
    DevelopmentSubprocessSpecRunner,
    DockerRunnerCommand,
    DockerSpecRunner,
    RunnerConfigurationError,
    SpecRunner,
    SpecRunResult,
)
from price_monitor.repair.versions import (
    ActivationResult,
    ImmutableVersionConflictError,
    SpecVersion,
    SpecVersionError,
    SpecVersionStore,
    StaleCandidateError,
    UnknownSpecError,
)
from price_monitor.repair.workflow import (
    GuardedRepairWorkflow,
    RepairEvaluation,
    UnvalidatedRepairError,
)

__all__ = [
    "ActivationResult",
    "DeclarativeRepairPolicy",
    "DeterministicSelectorProposalProvider",
    "DevelopmentSubprocessSpecRunner",
    "DisabledRepairProvider",
    "DockerRunnerCommand",
    "DockerSpecRunner",
    "FixtureReview",
    "GuardedRepairWorkflow",
    "ImmutableVersionConflictError",
    "ManualRepairProvider",
    "OpenAISelectorProposalProvider",
    "PolicyViolation",
    "RepairEvaluation",
    "RepairFixture",
    "RepairPolicyReport",
    "RepairProposal",
    "RepairProvider",
    "RepairRequest",
    "RepairReviewReport",
    "RunnerConfigurationError",
    "SelectorAddition",
    "SpecRunResult",
    "SpecRunner",
    "SpecVersion",
    "SpecVersionError",
    "SpecVersionStore",
    "StaleCandidateError",
    "StructuredSelectorRepair",
    "TrustedRepairReviewer",
    "UnknownSpecError",
    "UnvalidatedRepairError",
    "validate_repair_scope",
]
