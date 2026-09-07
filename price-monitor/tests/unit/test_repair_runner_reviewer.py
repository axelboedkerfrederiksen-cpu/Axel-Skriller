from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from price_monitor.domain.enums import Availability, FetchMode
from price_monitor.domain.types import FetchedPage, ScrapeTarget
from price_monitor.repair.providers import (
    DeterministicSelectorProposalProvider,
    RepairRequest,
)
from price_monitor.repair.reviewer import RepairFixture, TrustedRepairReviewer
from price_monitor.repair.runner import (
    DevelopmentSubprocessSpecRunner,
    DockerRunnerCommand,
    RunnerConfigurationError,
)
from price_monitor.scrapers.spec import SelectorRule, SiteSpec


def _baseline() -> SiteSpec:
    return SiteSpec(
        key="demo_store",
        revision="v1",
        allowed_hosts=("shop.example",),
        product_container=".product",
        name=(SelectorRule(selector=".name"),),
        price=(SelectorRule(selector=".price"),),
        availability=(SelectorRule(selector=".availability"),),
    )


def _page(html: str, suffix: str) -> FetchedPage:
    url = f"https://shop.example/products/{suffix}"
    return FetchedPage(
        requested_url=url,
        final_url=url,
        html=html,
        status_code=200,
        duration_ms=5,
        content_sha256=hashlib.sha256(html.encode()).hexdigest(),
    )


def _target(suffix: str) -> ScrapeTarget:
    return ScrapeTarget(
        competitor_product_id=suffix,
        url=f"https://shop.example/products/{suffix}",
        allowed_hosts=("shop.example",),
        adapter_key="demo_store",
        adapter_revision="v1",
        fetch_mode=FetchMode.HTTP,
        expected_name="Alpha Widget",
        expected_currency="USD",
        minimum_valid_price=Decimal("1"),
        maximum_valid_price=Decimal("100"),
    )


def _fixture(name: str, cohort: str, html: str, price: str) -> RepairFixture:
    return RepairFixture(
        name=name,
        cohort=cohort,  # type: ignore[arg-type]
        page=_page(html, name),
        target=_target(name),
        expected_name="Alpha Widget",
        expected_price=Decimal(price),
        expected_currency="USD",
        expected_availability=Availability.IN_STOCK,
    )


def test_development_runner_is_explicitly_forbidden_in_production() -> None:
    with pytest.raises(RunnerConfigurationError, match="development-only"):
        DevelopmentSubprocessSpecRunner(environment="production")


def test_docker_command_has_production_sandbox_controls() -> None:
    command = DockerRunnerCommand(image="registry.example/price-monitor-repair:sha256").build()

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert command[-3:] == ("-I", "-m", "price_monitor.repair._spec_worker")


def test_trusted_reviewer_runs_old_new_and_unseen_holdout_fixtures() -> None:
    baseline = _baseline()
    new_html = """
        <article class="product">
          <h1 class="product-title">Alpha Widget</h1>
          <span class="product-price">$12.00</span>
          <span class="availability">In stock</span>
        </article>
    """
    proposal = DeterministicSelectorProposalProvider().propose(
        RepairRequest(
            baseline=baseline,
            new_html=new_html,
            failed_fields=frozenset({"name", "price"}),
        )
    )
    assert proposal is not None
    fixtures = (
        _fixture(
            "old-page",
            "old",
            """
                <article class="product"><h2 class="name">Alpha Widget</h2>
                <span class="price">$10.00</span>
                <span class="availability">In stock</span></article>
            """,
            "10.00",
        ),
        _fixture("new-page", "new", new_html, "12.00"),
        _fixture(
            "holdout-page",
            "holdout",
            """
                <article class="product"><h1 class="product-title">Alpha Widget</h1>
                <span class="product-price">$13.25</span>
                <span class="availability">In stock</span></article>
            """,
            "13.25",
        ),
    )
    reviewer = TrustedRepairReviewer(
        DevelopmentSubprocessSpecRunner(environment="test", timeout_seconds=10)
    )

    report = reviewer.review(
        baseline=baseline,
        candidate=proposal.candidate,
        fixtures=fixtures,
        permitted_selector_fields=frozenset({"name", "price"}),
    )

    assert report.accepted
    assert len(report.fixtures) == 3
    assert all(fixture.passed for fixture in report.fixtures)


def test_reviewer_rejects_incomplete_fixture_cohorts_without_execution() -> None:
    baseline = _baseline()
    candidate = SiteSpec.model_validate(
        {
            **baseline.model_dump(mode="python"),
            "revision": "repair-1",
            "price": (SelectorRule(selector=".new-price"), *baseline.price),
        }
    )
    reviewer = TrustedRepairReviewer(
        DevelopmentSubprocessSpecRunner(environment="test", timeout_seconds=10)
    )

    report = reviewer.review(
        baseline=baseline,
        candidate=candidate,
        fixtures=(
            _fixture(
                "new-only",
                "new",
                '<article class="product"><h2 class="name">Alpha Widget</h2>'
                '<span class="new-price">$10.00</span></article>',
                "10.00",
            ),
        ),
    )

    assert not report.accepted
    assert report.fixtures == ()
    assert {item.code for item in report.fixture_policy_violations} == {"missing_fixture_cohort"}
