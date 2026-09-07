from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from price_monitor.domain.enums import Availability
from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.repair.policy import (
    DeclarativeRepairPolicy,
    PolicyViolation,
    RepairPolicyReport,
)
from price_monitor.repair.runner import SpecRunner, SpecRunResult
from price_monitor.scrapers.spec import SiteSpec

FixtureCohort = Literal["old", "new", "holdout"]


@dataclass(frozen=True, slots=True)
class RepairFixture:
    name: str
    cohort: FixtureCohort
    page: FetchedPage
    target: ScrapeTarget
    expected_name: str | None = None
    expected_price: Decimal | None = None
    expected_currency: str | None = None
    expected_availability: Availability | None = None
    price_tolerance: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 200:
            raise ValueError("fixture name must contain 1-200 characters")
        if self.price_tolerance < 0:
            raise ValueError("price_tolerance cannot be negative")


@dataclass(frozen=True, slots=True)
class FixtureReview:
    fixture_name: str
    cohort: FixtureCohort
    passed: bool
    failures: tuple[str, ...]
    run: SpecRunResult


@dataclass(frozen=True, slots=True)
class RepairReviewReport:
    accepted: bool
    policy: RepairPolicyReport
    fixture_policy_violations: tuple[PolicyViolation, ...]
    fixtures: tuple[FixtureReview, ...]


class TrustedRepairReviewer:
    """Deterministic deployment gate for a declarative SiteSpec candidate."""

    def __init__(
        self,
        runner: SpecRunner,
        *,
        policy: DeclarativeRepairPolicy | None = None,
        required_cohorts: frozenset[FixtureCohort] = frozenset({"old", "new", "holdout"}),
    ) -> None:
        self._runner = runner
        self._policy = policy or DeclarativeRepairPolicy()
        self._required_cohorts = required_cohorts

    def review(
        self,
        *,
        baseline: SiteSpec,
        candidate: SiteSpec,
        fixtures: tuple[RepairFixture, ...],
        permitted_selector_fields: frozenset[str] | None = None,
    ) -> RepairReviewReport:
        policy_report = self._policy.validate(
            baseline,
            candidate,
            permitted_selector_fields=permitted_selector_fields,
        )
        fixture_violations = self._validate_fixture_set(baseline, fixtures)
        if not policy_report.accepted or fixture_violations:
            return RepairReviewReport(
                accepted=False,
                policy=policy_report,
                fixture_policy_violations=fixture_violations,
                fixtures=(),
            )

        reviews = tuple(
            self._review_fixture(candidate=candidate, fixture=fixture) for fixture in fixtures
        )
        return RepairReviewReport(
            accepted=all(review.passed for review in reviews),
            policy=policy_report,
            fixture_policy_violations=(),
            fixtures=reviews,
        )

    def _validate_fixture_set(
        self, baseline: SiteSpec, fixtures: tuple[RepairFixture, ...]
    ) -> tuple[PolicyViolation, ...]:
        violations: list[PolicyViolation] = []
        names = [fixture.name for fixture in fixtures]
        if len(set(names)) != len(names):
            violations.append(PolicyViolation("duplicate_fixture", "fixture names must be unique"))
        cohorts = {fixture.cohort for fixture in fixtures}
        for missing in sorted(self._required_cohorts - cohorts):
            violations.append(
                PolicyViolation(
                    "missing_fixture_cohort",
                    f"review requires at least one {missing} fixture",
                )
            )
        for fixture in fixtures:
            if fixture.target.adapter_key != baseline.key:
                violations.append(
                    PolicyViolation(
                        "fixture_adapter_mismatch",
                        f"fixture {fixture.name!r} targets another adapter",
                    )
                )
            if fixture.target.adapter_revision != baseline.revision:
                violations.append(
                    PolicyViolation(
                        "fixture_revision_mismatch",
                        f"fixture {fixture.name!r} is not pinned to the baseline revision",
                    )
                )
            if set(fixture.target.allowed_hosts) != set(baseline.allowed_hosts):
                violations.append(
                    PolicyViolation(
                        "fixture_hosts_mismatch",
                        f"fixture {fixture.name!r} has a different host allowlist",
                    )
                )
        return tuple(violations)

    def _review_fixture(self, *, candidate: SiteSpec, fixture: RepairFixture) -> FixtureReview:
        target = fixture.target.model_copy(
            update={
                "adapter_key": candidate.key,
                "adapter_revision": candidate.revision,
                "fetch_mode": candidate.fetch_mode,
            }
        )
        run = self._runner.run(spec=candidate, page=fixture.page, target=target)
        failures: list[str] = []
        if run.error_type is not None:
            failures.append(f"runner error {run.error_type}: {run.error_message}")
        elif run.validation is None or run.product is None:
            failures.append("runner returned no extracted product or validation result")
        else:
            if not run.validation.accepted:
                error_codes = ", ".join(
                    issue.code for issue in run.validation.issues if issue.severity == "error"
                )
                failures.append(f"validation rejected extraction: {error_codes or 'unknown'}")
            product = run.product
            if fixture.expected_name is not None and product.name != fixture.expected_name:
                failures.append(
                    f"name mismatch: expected {fixture.expected_name!r}, got {product.name!r}"
                )
            if fixture.expected_price is not None and (
                abs(product.price - fixture.expected_price) > fixture.price_tolerance
            ):
                failures.append(
                    f"price mismatch: expected {fixture.expected_price}, got {product.price}"
                )
            if (
                fixture.expected_currency is not None
                and product.currency != fixture.expected_currency.upper()
            ):
                failures.append(
                    f"currency mismatch: expected {fixture.expected_currency.upper()}, "
                    f"got {product.currency}"
                )
            if (
                fixture.expected_availability is not None
                and product.availability != fixture.expected_availability
            ):
                failures.append(
                    f"availability mismatch: expected {fixture.expected_availability}, "
                    f"got {product.availability}"
                )
        return FixtureReview(
            fixture_name=fixture.name,
            cohort=fixture.cohort,
            passed=not failures,
            failures=tuple(failures),
            run=run,
        )
