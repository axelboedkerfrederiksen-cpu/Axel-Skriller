from __future__ import annotations

from pathlib import Path

import pytest

from price_monitor.repair.versions import (
    ImmutableVersionConflictError,
    SpecVersionError,
    SpecVersionStore,
    StaleCandidateError,
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
    )


def _candidate(revision: str = "repair-1", selector: str = ".new-price") -> SiteSpec:
    baseline = _baseline()
    return SiteSpec.model_validate(
        {
            **baseline.model_dump(mode="python"),
            "revision": revision,
            "price": (SelectorRule(selector=selector), *baseline.price),
        }
    )


def test_version_store_uses_packaged_baseline_then_activates_and_rolls_back(
    tmp_path: Path,
) -> None:
    baseline = _baseline()
    store = SpecVersionStore(tmp_path, [baseline])

    assert store.get_active(baseline.key).source == "packaged"
    staged = store.stage_candidate(_candidate(), expected_base_revision="v1")
    assert staged.source == "staged"
    assert (tmp_path / staged.relative_path).is_file()  # type: ignore[arg-type]

    activation = store.activate(baseline.key, "repair-1", expected_active_revision="v1")
    assert activation.active.spec.revision == "repair-1"
    assert activation.previous is not None
    assert activation.previous.spec.revision == "v1"
    assert store.get_active(baseline.key).source == "versioned"

    rollback = store.rollback(
        baseline.key, expected_active_revision=activation.active.spec.revision
    )
    assert rollback.active.spec == baseline
    assert rollback.active.source == "packaged"
    assert store.get_revision(baseline.key, "repair-1").spec == _candidate()


def test_staging_rejects_stale_base_and_immutable_revision_conflicts(
    tmp_path: Path,
) -> None:
    store = SpecVersionStore(tmp_path, [_baseline()])
    with pytest.raises(StaleCandidateError):
        store.stage_candidate(_candidate(), expected_base_revision="outdated")

    store.stage_candidate(_candidate(), expected_base_revision="v1")
    with pytest.raises(ImmutableVersionConflictError):
        store.stage_candidate(_candidate(selector=".different-price"), expected_base_revision="v1")


def test_version_store_rejects_path_components(tmp_path: Path) -> None:
    store = SpecVersionStore(tmp_path, [_baseline()])
    with pytest.raises(SpecVersionError):
        store.get_active("../demo_store")
