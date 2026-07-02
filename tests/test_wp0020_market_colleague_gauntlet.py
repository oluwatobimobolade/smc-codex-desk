from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from PIL import Image

import smc_desk.colleague.wp0020_gauntlet as gauntlet


def _write_png(path: str | Path, size: tuple[int, int] = (640, 360)) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(18, 22, 28)).save(path)


def _write_15m_csv(path: Path, bars: int = 720) -> Path:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(bars):
        ts = start + timedelta(minutes=15 * index)
        drift = index * 0.35
        wave = ((index % 32) - 16) * 1.2
        open_price = 100_000 + drift + wave
        close = open_price + (2.5 if index % 2 == 0 else -1.8)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": round(open_price, 2),
                "high": round(max(open_price, close) + 8.0, 2),
                "low": round(min(open_price, close) - 8.0, 2),
                "close": round(close, 2),
                "volume": 1000 + index % 50,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _patch_renderers(monkeypatch) -> None:
    monkeypatch.setattr(
        gauntlet,
        "render_raw_chart",
        lambda _df, symbol, timeframe, output_path: _write_png(output_path, (640, 360)),
    )
    monkeypatch.setattr(
        gauntlet,
        "render_smc_annotated",
        lambda _df, _analysis, output_path, min_conf="medium", title=None: _write_png(output_path, (800, 420)),
    )
    monkeypatch.setattr(
        gauntlet,
        "render_mtf_mosaic",
        lambda _dfs, _analyses, output_path, title="": _write_png(output_path, (900, 620)),
    )


def _patch_colleague_brain(monkeypatch) -> None:
    def valid_perception(tf: str) -> dict:
        now = datetime(2026, 6, 8, 11, 45, tzinfo=timezone.utc)
        return {
            "decision_time": now.isoformat(),
            "swings": {"local": [], "internal": [], "external": []},
            "structure_state": {
                "current_direction": "bullish",
                "protected_high_id": None,
                "protected_low_id": None,
                "last_confirmed_external_high": None,
                "last_confirmed_external_low": None,
                "last_confirmed_internal_high": None,
                "last_confirmed_internal_low": None,
                "last_external_break_id": None,
                "last_internal_break_id": None,
                "internal_direction": "bullish",
                "protected_internal_high_id": None,
                "protected_internal_low_id": None,
                "current_as_of": now.isoformat(),
            },
            "structure_breaks": [],
            "fvgs": [],
            "liquidity_levels": [],
            "sweeps": [],
            "order_blocks": [],
            "inducements": [],
            "poi_grade_fvgs": [],
            "candle_count": 120,
            "last_close": now.isoformat(),
            "last_price": "100000.0",
        }

    class Truth:
        ok = True

        def to_dict(self) -> dict:
            return {
                "status": "PASS",
                "refuse_perception": False,
                "provider_count": 1,
                "timeframe_summaries": [],
                "issues": [],
            }

    class Result:
        truth_report = Truth()

        def to_dict(self) -> dict:
            perception_by_tf = {tf: valid_perception(tf) for tf in gauntlet.TIMEFRAMES}
            return {
                "pipeline": "colleague_brain_v2",
                "authority": {
                    "market_truth": "hard_gate",
                    "decision": "observe_only_no_execution",
                    "paper_execution": "disabled",
                    "live_execution": "disabled",
                    "capital_risk": 0,
                },
                "truth_report": self.truth_report.to_dict(),
                "perception_by_tf": perception_by_tf,
                "regime": {
                    "structure_regime": "ranging",
                    "volatility_regime": "compression",
                    "liquidity_regime": "accumulation",
                    "confidence": 0.72,
                },
                "contradiction": {
                    "outcome": "WAIT",
                    "dominant_direction": "bullish",
                    "contradiction_score": 0.25,
                    "blocks_signal": True,
                    "reasons": ["unit_test_wait_state"],
                },
                "uncertainty": {
                    "signal_confidence": 0.55,
                    "final_verdict": "NO_SIGNAL",
                    "blocks_signal": True,
                },
                "refusal": {
                    "final_action": "NO_SIGNAL",
                    "perception_allowed": True,
                    "signal_allowed": False,
                    "refused": True,
                    "reasons": ["unit_test_refusal"],
                    "blocking_codes": ["unit_test_block"],
                },
                "final_action": "NO_SIGNAL",
                "final_state": "WATCH_BULLISH_RETRACE_TO_DEMAND",
                "watch_state": {
                    "final_state": "WATCH_BULLISH_RETRACE_TO_DEMAND",
                    "final_action": "NO_SIGNAL",
                    "signal_allowed": False,
                    "direction": "bullish",
                    "active_poi": None,
                    "reasons": ["unit_test_watch"],
                },
                "structure_hierarchy": {
                    tf: {
                        "timeframe": tf,
                        "external_bias": "bullish",
                        "depth_status": "test_depth",
                        "dealing_range": None,
                        "evidence": {},
                    }
                    for tf in gauntlet.TIMEFRAMES
                },
                "memory_record": {"decision_id": "unit-test"},
            }

    def fake_brain(*, memory_path=None, **_kwargs):
        if memory_path:
            Path(memory_path).parent.mkdir(parents=True, exist_ok=True)
            Path(memory_path).write_text(json.dumps({"decision_id": "unit-test"}) + "\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(gauntlet, "run_colleague_brain_v2", fake_brain)


def test_wp0020_gauntlet_builds_all_required_artifacts_without_execution_authority(monkeypatch, tmp_path):
    _patch_renderers(monkeypatch)
    _patch_colleague_brain(monkeypatch)
    source = _write_15m_csv(tmp_path / "BTCUSDT_15m.csv")
    output = tmp_path / "gauntlet"

    result = gauntlet.run_wp0020_gauntlet(
        symbol="BTCUSDT",
        source=source,
        output_dir=output,
        mode="csv",
        visual_mode="skip",
    )

    assert result.status == "PARTIAL_PASS"
    assert result.failed_layer == "07_tradingview_visual"
    for folder in gauntlet.GAUNTLET_STRUCTURE:
        assert (output / folder).is_dir()

    report = json.loads((output / "11_final_report" / "gauntlet_report.json").read_text(encoding="utf-8"))
    summary = report["full_summary"]
    assert report["market_edge_claimed"] is False
    assert report["paper_execution"] == "disabled"
    assert report["live_execution"] == "disabled"
    assert report["capital_risk"] == 0
    assert summary["clean_charts_generated"] == 4
    assert summary["legacy_debug_charts_generated"] == 4
    assert summary["decision_authority_story_charts_generated"] == 4
    assert summary["tradingview_screenshots_captured"] == 0
    assert summary["visual_reconciliation_result"] == "REVIEW_REQUIRED"
    assert summary["final_colleague_action"] == "NO_SIGNAL"
    assert summary["thesis_generated"] is True
    assert summary["memory_record_count"] == 1
    assert summary["research_event_count"] > 0
    assert summary["pending_outcome_contract"] == "pending_observation"
    assert report["stage_results"]["01_verified_ohlcv"]["tradingview_used_as_market_truth"] is False
    assert report["stage_results"]["08_visual_reconciliation"]["market_truth_changed"] is False
    assert report["stage_results"]["04_debug_legacy_annotations"]["chart_authority"] == "debug_only_legacy_not_decision_authority"
    assert report["stage_results"]["04a_story_charts"]["chart_type"] == "v2_story_charts"


def test_wp0020_live_failure_stops_before_perception(monkeypatch, tmp_path):
    _patch_renderers(monkeypatch)

    def forbidden_brain(**_kwargs):
        raise AssertionError("perception/cognition must not run after unverified OHLCV")

    def fake_route_health(**_kwargs):
        return SimpleNamespace(to_dict=lambda: {"overall": "FAIL", "required_action": "NO_VALID_LIVE_TRADE"})

    def fake_acquire(**_kwargs):
        raise RuntimeError("simulated data route outage")

    monkeypatch.setattr(gauntlet, "run_colleague_brain_v2", forbidden_brain)
    monkeypatch.setattr(gauntlet, "run_route_health_preflight", fake_route_health)
    monkeypatch.setattr(gauntlet, "acquire_verified_closed_ohlcv", fake_acquire)

    result = gauntlet.run_wp0020_gauntlet(
        symbol="BTCUSDT",
        output_dir=tmp_path / "live_fail",
        mode="live",
        visual_mode="skip",
        live_limit=10,
        min_live_bars=2,
    )

    assert result.status == "PARTIAL_PASS"
    assert result.failed_layer == "01_verified_ohlcv"
    failure = json.loads(
        (result.output_dir / "01_verified_ohlcv" / "verified_closed_ohlcv_failure.json").read_text(encoding="utf-8")
    )
    assert failure["required_action"] == "NO_VALID_LIVE_TRADE"
    assert failure["tradingview_used_as_market_truth"] is False
    assert not (result.output_dir / "05_perception" / "perception_events.json").exists()
