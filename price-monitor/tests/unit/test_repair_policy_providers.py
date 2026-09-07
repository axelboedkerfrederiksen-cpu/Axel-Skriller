from __future__ import annotations

from price_monitor.repair.policy import DeclarativeRepairPolicy
from price_monitor.repair.providers import (
    DeterministicSelectorProposalProvider,
    DisabledRepairProvider,
    ManualRepairProvider,
    RepairRequest,
)
from price_monitor.scrapers.spec import SelectorRule, SiteSpec


def _baseline() -> SiteSpec:
    return SiteSpec(
        key="demo_store",
        revision="v1",
        allowed_hosts=("shop.example",),
        product_container=".product",
        name=(SelectorRule(selector=".legacy-name"),),
        price=(SelectorRule(selector=".legacy-price"),),
    )


def test_deterministic_provider_only_adds_allowlisted_matching_selectors() -> None:
    request = RepairRequest(
        baseline=_baseline(),
        failed_fields=frozenset({"name", "price"}),
        new_html="""
            <html><head><meta property="og:title" content="Safe Product"></head>
            <body><article class="product"><span data-price="$19.99"></span></article></body>
            </html>
        """,
    )

    proposal = DeterministicSelectorProposalProvider().propose(request)

    assert proposal is not None
    assert proposal.changed_fields == ("name", "price")
    assert proposal.candidate.name[0].selector == 'meta[property="og:title"]'
    assert proposal.candidate.price[0].selector == "[data-price]"
    assert proposal.candidate.name[-1] == request.baseline.name[-1]
    assert proposal.candidate.price[-1] == request.baseline.price[-1]
    assert (
        DeclarativeRepairPolicy()
        .validate(
            request.baseline,
            proposal.candidate,
            permitted_selector_fields=request.failed_fields,
        )
        .accepted
    )


def test_provider_boundaries_do_not_accept_python_patches() -> None:
    request = RepairRequest(baseline=_baseline(), new_html="<html></html>")
    assert DisabledRepairProvider().propose(request) is None
    assert ManualRepairProvider().propose(request) is None

    candidate = SiteSpec.model_validate(
        {
            **request.baseline.model_dump(mode="python"),
            "revision": "manual-1",
            "price": (
                SelectorRule(selector=".manual-price"),
                *request.baseline.price,
            ),
        }
    )
    proposal = ManualRepairProvider(candidate).propose(request)
    assert proposal is not None
    assert proposal.candidate == candidate


def test_policy_rejects_host_changes_rule_removal_and_out_of_scope_fields() -> None:
    baseline = _baseline()
    candidate = SiteSpec.model_validate(
        {
            **baseline.model_dump(mode="python"),
            "revision": "unsafe-1",
            "allowed_hosts": ("attacker.example",),
            "price": (SelectorRule(selector=".replacement"),),
        }
    )

    report = DeclarativeRepairPolicy().validate(baseline, candidate)

    assert not report.accepted
    assert {violation.code for violation in report.violations} >= {
        "field_out_of_scope",
        "rule_removed",
    }


def test_policy_limits_changes_to_reported_failed_fields() -> None:
    baseline = _baseline()
    candidate = SiteSpec.model_validate(
        {
            **baseline.model_dump(mode="python"),
            "revision": "too-broad-1",
            "price": (SelectorRule(selector=".new-price"), *baseline.price),
        }
    )

    report = DeclarativeRepairPolicy().validate(
        baseline, candidate, permitted_selector_fields=frozenset({"name"})
    )
    assert not report.accepted
    assert any(violation.field == "price" for violation in report.violations)
