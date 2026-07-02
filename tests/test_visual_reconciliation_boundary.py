from __future__ import annotations

import json
from pathlib import Path

from smc_desk.colleague.wp0020_gauntlet import reconcile_engine_vs_tradingview


def test_missing_tradingview_visuals_request_review_without_changing_market_truth(tmp_path):
    report = reconcile_engine_vs_tradingview(
        engine_chart_manifest={"status": "PASS", "charts": {}},
        tradingview_manifest={
            "status": "SKIPPED",
            "tradingview_used_as_market_truth": False,
            "screenshots": {},
        },
        output_dir=tmp_path,
    )

    assert report["status"] == "REVIEW_REQUIRED"
    assert report["review_required"] is True
    assert report["market_truth_changed"] is False
    assert report["tradingview_used_as_market_truth"] is False
    persisted = json.loads((tmp_path / "visual_reconciliation_report.json").read_text(encoding="utf-8"))
    assert persisted == report


def test_incomplete_tradingview_screenshots_remain_audit_only_with_context_mismatch(tmp_path):
    screenshot = tmp_path / "tradingview_15m.png"
    screenshot.write_bytes(b"not opened by reconciliation")

    report = reconcile_engine_vs_tradingview(
        engine_chart_manifest={"status": "PASS", "charts": {}},
        tradingview_manifest={
            "status": "PASS",
            "tradingview_used_as_market_truth": False,
            "screenshots": {"15m": str(screenshot)},
        },
        output_dir=tmp_path / "reconcile",
    )

    assert report["status"] == "VISUAL_CONTEXT_UNVERIFIED"
    assert report["review_required"] is True
    assert report["context_mismatch"] is False
    assert report["screenshot_checks"]["15m"]["image_exists"] is True
    assert report["screenshot_checks"]["15m"]["image_opened"] is False
    assert set(report["missing_timeframes"]) == {"1h", "4h", "1d"}
    assert report["market_truth_changed"] is False
    assert report["tradingview_used_as_market_truth"] is False
