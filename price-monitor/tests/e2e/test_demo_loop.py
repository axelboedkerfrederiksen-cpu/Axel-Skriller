from __future__ import annotations

import asyncio
from pathlib import Path

from price_monitor.demo import run_demo


def test_complete_scrape_change_break_repair_reject_loop(tmp_path: Path) -> None:
    report = asyncio.run(run_demo(tmp_path))

    assert report.initial_price == "51.7700"
    assert report.changed_price == "47.9900"
    assert report.previous_price == "51.7700"
    assert report.price_change_kind == "decrease"
    assert report.history_rows_before_failure == 2
    assert report.failure_status == "failed"
    assert report.repair_created
    assert report.bad_candidate_rejected
    assert report.good_candidate_validated
    assert report.deployed_revision.startswith("repair-")
    assert report.repaired_scrape_status == "succeeded"
    assert report.history_rows_after_repair == 3
    assert report.rollback_revision_available == "1"
    assert not report.network_used
