from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from smc_desk.brain import ManualJSONProvider
from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, parse_ai_smc_decision
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.colleague.orchestrator_v3 import (
    _effective_context_depth_report,
    _run_perception_candidates,
    _suppress_blocked_definition_timeframes,
    run_ai_smc_orchestrator_v3,
)
from smc_desk.colleague.smc_thesis_ai_v1 import (
    _narrative_context,
    build_smc_thesis_ai_v1,
    render_smc_thesis_ai_v1_markdown,
)
from smc_desk.data.historical_backfill import DEFAULT_MINIMUM_DEPTH, FOREX_MINIMUM_DEPTH, build_context_depth_report
from smc_desk.gauntlet.wp0035_ai_brain_gauntlet import run_wp0035_ai_brain_gauntlet
from smc_desk.rendering.smc_trader_annotation_renderer import _assign_level_label_positions
from smc_desk.session import summarize_session_context


def _df(rows: int = 80, timeframe: str = "15min", base: float = 100.0) -> pd.DataFrame:
    freq = "1D" if timeframe == "1d" else timeframe
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01", periods=rows, freq=freq, tz="UTC"),
            "open": [base + (i % 9) * 0.08 for i in range(rows)],
            "high": [base + 1.0 + (i % 9) * 0.08 for i in range(rows)],
            "low": [base - 1.0 - (i % 5) * 0.08 for i in range(rows)],
            "close": [base + (i % 7) * 0.04 for i in range(rows)],
            "volume": [1000 + i for i in range(rows)],
        }
    )


def _timeframe_dfs(rows: int = 80) -> dict[str, pd.DataFrame]:
    return {
        "15m": _df(rows, "15min"),
        "1h": _df(rows, "1h"),
        "4h": _df(rows, "4h"),
        "1d": _df(rows, "1d"),
    }


def _detector_candidates() -> dict[str, Any]:
    return {
        "15m": {
            "sweeps": [{"object_id": "sweep1", "side": "buy_side", "price": 102.0, "direction": "bearish"}],
            "structure_breaks": [{"object_id": "break1", "direction": "bearish", "price": 98.0}],
            "fvgs": [{"object_id": "fvg1", "direction": "bearish", "price_low": 99.6, "price_high": 100.4}],
            "order_blocks": [{"object_id": "poi1", "direction": "bearish", "price_low": 100.0, "price_high": 101.0}],
            "liquidity_levels": [{"object_id": "liq1", "side": "sell_side", "price": 95.0}],
        }
    }


def _payload(*, trade_ready: bool = False, active_range: Mapping[str, Any] | None = None) -> dict[str, Any]:
    active = dict(
        active_range
        or {
            "timeframe": "1h",
            "high": 103.0,
            "low": 95.0,
            "equilibrium": 99.0,
            "price_location": "premium",
            "source": "protected_swing_pair",
            "range_id": "range1",
            "protected_high": 103.0,
            "protected_low": 95.0,
            "width_atr": 8.0,
            "max_allowed_width_atr": 24.0,
            "evidence": ["Protected swing pair."],
        }
    )
    payload = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY" if trade_ready else "WATCH_ONLY",
        "setup_grade": "A" if trade_ready else "C",
        "direction": "bearish",
        "setup_model": "bearish_sweep_to_supply",
        "bias_summary": {"daily": "bearish", "4h": "bearish", "1h": "bearish", "final_bias": "bearish", "evidence": ["HTF bearish."]},
        "active_range": active,
        "liquidity_story": {
            "obvious_liquidity": [{"liquidity_id": "bsl1", "side": "buy_side", "price": 102.0, "label": "buy-side liquidity"}],
            "swept_liquidity": [{"liquidity_id": "sweep1", "side": "buy_side", "price": 102.0, "label": "buy-side sweep", "evidence_object_ids": ["sweep1"]}] if trade_ready else [],
            "unswept_liquidity": [{"liquidity_id": "liq1", "side": "sell_side", "price": 95.0, "label": "sell-side target", "evidence_object_ids": ["liq1"]}] if trade_ready else [],
            "narrative": "Watch the active range; execute only when all evidence is confirmed.",
        },
        "displacement_assessment": {
            "direction": "bearish" if trade_ready else "none",
            "quality": "clean" if trade_ready else "none",
            "structure_broken": trade_ready,
            "evidence_object_ids": ["break1"] if trade_ready else [],
            "summary": "" if not trade_ready else "Clean bearish displacement.",
        },
        "active_poi": {
            "poi_id": "poi1" if trade_ready else None,
            "timeframe": "15m" if trade_ready else None,
            "kind": "supply" if trade_ready else None,
            "direction": "bearish" if trade_ready else "unknown",
            "price_low": 100.0 if trade_ready else None,
            "price_high": 101.0 if trade_ready else None,
            "freshness": "fresh" if trade_ready else None,
            "evidence_object_ids": ["poi1"] if trade_ready else [],
            "summary": "" if not trade_ready else "Active supply.",
        },
        "entry_plan": {
            "entry_ready": trade_ready,
            "entry_timeframe": "15m",
            "refinement_timeframe": "5m",
            "entry_price": 100.0 if trade_ready else None,
            "entry_zone_low": 100.0 if trade_ready else None,
            "entry_zone_high": 100.4 if trade_ready else None,
            "signal_type": "supply rejection" if trade_ready else None,
            "required_confirmation": ["reject"] if trade_ready else [],
            "evidence_object_ids": ["poi1"] if trade_ready else [],
            "summary": "Ready." if trade_ready else "No entry.",
        },
        "stop_loss_plan": {
            "stop_price": 101.5 if trade_ready else None,
            "structural_invalidation_price": 101.5 if trade_ready else None,
            "source": "above_supply" if trade_ready else None,
            "buffer_notes": "structural" if trade_ready else None,
            "evidence_object_ids": ["poi1"] if trade_ready else [],
            "summary": "SL equals invalidation." if trade_ready else "No stop.",
        },
        "target_plan": {
            "targets": [{"price": 95.0, "label": "TP1", "timeframe": "1h", "reason": "sell-side liquidity", "evidence_object_ids": ["liq1"]}] if trade_ready else [],
            "model_completion_liquidity_id": "liq1" if trade_ready else None,
            "summary": "Target sell-side liquidity." if trade_ready else "No target.",
        },
        "rr_status": {"rr": 3.3333 if trade_ready else None, "minimum_rr": 3.0, "pass_rr": trade_ready, "notes": "3R+." if trade_ready else "No RR."},
        "invalidation": {"invalidation_price": 101.5 if trade_ready else active.get("high"), "condition": "Invalid above structure.", "source": "protected_high", "evidence_object_ids": []},
        "annotation_plan": {
            "chart_template": "trade_plan_chart" if trade_ready else "watch_chart",
            "show_trade_box": trade_ready,
            "labels": [{"text": "Watch state", "kind": "state"}],
            "levels": [
                {"label": "Entry", "kind": "entry", "price": 100.0},
                {"label": "SL", "kind": "stop", "price": 101.5},
                {"label": "TP1", "kind": "target", "price": 95.0},
            ]
            if trade_ready
            else [],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "passed" if trade_ready else "not_applicable",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [],
            "remaining_uncertainties": [],
        },
        "final_thesis": "Validated plan." if trade_ready else "Watch only.",
    }
    return payload


def _authority_range(direction: str = "bearish") -> dict[str, Any]:
    return {
        "schema": "active_range_authority_v1",
        "status": "RESOLVED_ACTIVE_RANGE",
        "selected_range": {
            "status": "RESOLVED_ACTIVE_RANGE",
            "timeframe": "1h",
            "direction": direction,
            "range_high": 103.0,
            "range_low": 95.0,
            "width_atr": 8.0,
            "max_width_atr": 24.0,
            "source": "protected_swing_pair",
        },
    }


def _tool_module(name: str):
    path = Path(__file__).resolve().parents[1] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_renderer_offsets_same_price_level_labels():
    levels = [
        {"kind": "liquidity", "label": "RANGE HIGH", "low": 7.018, "high": 7.018},
        {"kind": "invalidation", "label": "INVALIDATION", "low": 7.018, "high": 7.018},
    ]
    positioned = _assign_level_label_positions(levels, low=6.0, high=8.0)
    assert len({item["label_y"] for item in positioned}) == 2


def test_renderer_separates_nearby_ob_bos_and_idm_captions_without_moving_geometry():
    levels = [
        {"kind": "bos", "label": "BOS", "low": 75.70, "high": 75.70},
        {"kind": "order_block", "label": "BEARISH OB", "low": 75.76, "high": 75.95},
        {"kind": "idm", "label": "IDM", "low": 75.95, "high": 75.95},
    ]

    positioned = _assign_level_label_positions(levels, low=72.0, high=78.0)
    label_positions = sorted(item["label_y"] for item in positioned)

    assert all(right - left >= 6.0 * 0.018 for left, right in zip(label_positions, label_positions[1:]))
    assert positioned[1]["low"] == 75.76
    assert positioned[1]["high"] == 75.95


def test_evidence_pack_embeds_chart_bytes_for_vision_providers(tmp_path):
    image_path = tmp_path / "15m.png"
    image_path.write_bytes(b"fake-png-bytes")
    pack = build_smc_evidence_pack(symbol="BTCUSDT", timeframe_dfs={"15m": _df()}, chart_images={"15m": image_path}, embed_images=True)
    request = LLMCompletionRequest(prompt="x", evidence_pack=pack, chart_images=pack["chart_images"])
    assert request.chart_image_paths == [str(image_path)]
    assert request.chart_image_base64[0]["data"]
    assert request.chart_image_base64[0]["media_type"] == "image/png"


def test_manual_json_provider_is_exported_from_brain_package():
    provider = ManualJSONProvider(_payload(), is_real_reasoning=False)
    assert provider.provider_name == "manual_local_ai_workspace"


def test_session_context_uses_latest_utc_day_current_session_only():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-06-28 13:00Z", "2026-06-28 14:00Z", "2026-06-29 13:00Z", "2026-06-29 14:00Z"],
                utc=True,
            ),
            "open": [1, 1, 1, 1],
            "high": [150, 151, 201, 202],
            "low": [140, 139, 198, 199],
            "close": [145, 146, 200, 201],
        }
    )
    summary = summarize_session_context(df)
    assert summary["current_session"] == "New York"
    assert summary["session_date"] == "2026-06-29"
    assert summary["bars_in_session_sample"] == 2
    assert summary["session_high"] == 202.0
    assert summary["session_low"] == 198.0


def test_orchestrator_auto_runs_perception_when_candidates_are_missing(tmp_path):
    calls: list[LLMCompletionRequest] = []

    def complete(request: LLMCompletionRequest) -> dict[str, Any]:
        calls.append(request)
        return _payload(trade_ready=False)

    result = run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(90),
        provider=CallableAISMCProvider(complete, provider_name="local", model_name="manual", provider_mode="MANUAL_AI_ASSISTED_JSON"),
        output_dir=tmp_path,
        detector_candidates=None,
        enforce_minimum_depth=False,
    )
    assert result.report["perception_candidates"]["auto_perception_ran"] is True
    assert calls[0].evidence_pack["detector_candidates"]


def test_wp0035_tradingview_capture_is_optional_and_skipped_by_default(tmp_path):
    result = run_wp0035_ai_brain_gauntlet(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(),
        provider=ManualJSONProvider(_payload(), is_real_reasoning=False),
        output_dir=tmp_path,
        detector_candidates={},
        enforce_minimum_depth=False,
        capture_tradingview=False,
    )
    assert result.final_report["tradingview_visual_check"]["status"] == "SKIPPED"


def test_thesis_does_not_render_empty_none_none_claims():
    decision = parse_ai_smc_decision(_payload(trade_ready=False))
    result = validate_ai_smc_decision(decision, {"detector_candidates": {}})
    thesis = build_smc_thesis_ai_v1(validation_result=result, evidence_pack={})
    markdown = render_smc_thesis_ai_v1_markdown(thesis)
    assert "none none displacement" not in markdown.lower()
    assert "None None None-None" not in markdown


def test_validator_warns_when_direction_conflicts_with_active_range_direction():
    decision = parse_ai_smc_decision(_payload(trade_ready=False))
    result = validate_ai_smc_decision(
        decision,
        {"detector_candidates": {}, "active_range_authority": _authority_range(direction="bullish")},
    )
    assert result.status == "VALIDATED"
    assert any(issue.code == "direction_conflicts_with_active_range" and issue.severity == "warning" for issue in result.issues)
    assert any(issue["code"] == "direction_conflicts_with_active_range" for issue in result.official_decision["validation_issues"])


def test_forex_depth_profile_allows_shallower_forex_context():
    df = _df(850, "15min")
    default_report = build_context_depth_report({"15m": df}, minimum_depths=DEFAULT_MINIMUM_DEPTH)
    forex_report = build_context_depth_report({"15m": df}, minimum_depths=FOREX_MINIMUM_DEPTH)
    assert default_report["15m"]["context_depth_warning"] is True
    assert forex_report["15m"]["context_depth_warning"] is False


def test_depth_downgrade_uses_shared_trade_plan_stripping(tmp_path):
    result = run_ai_smc_orchestrator_v3(
        symbol="BTCUSDT",
        timeframe_dfs=_timeframe_dfs(40),
        provider=ManualJSONProvider(_payload(trade_ready=True), is_real_reasoning=True),
        output_dir=tmp_path,
        detector_candidates=_detector_candidates(),
        enforce_minimum_depth=True,
    )
    official = result.validation_result.official_decision
    assert result.validation_result.status == "REVIEW_REQUIRED"
    assert official["entry_plan"]["entry_price"] is None
    assert official["stop_loss_plan"]["stop_price"] is None
    assert official["target_plan"]["targets"] == []
    assert official["annotation_plan"]["show_trade_box"] is False
    assert {level["kind"] for level in official["annotation_plan"]["levels"]}.isdisjoint({"entry", "stop", "target"})
    assert any(issue.code == "context_depth_warning" for issue in result.validation_result.issues)


def test_gold_readiness_audit_reports_insufficient_ground_truth_without_faking(tmp_path):
    module = _tool_module("audit_ai_smc_gold_readiness")
    report = module.audit_gold_readiness(tmp_path / "missing_cases", minimum_cases=20)
    assert report["status"] == "INSUFFICIENT_GROUND_TRUTH"
    assert report["engine_weak_labels_promoted_to_gold"] is False


def test_trade_ready_replay_audit_counts_real_artifacts(tmp_path):
    decision_dir = tmp_path / "run" / "13_official_ai_decision"
    decision_dir.mkdir(parents=True)
    decision_dir.joinpath("official_decision.json").write_text(
        json.dumps({"symbol": "BTCUSDT", "official_state": "WATCH_ONLY", "validation_status": "VALIDATED"}),
        encoding="utf-8",
    )
    module = _tool_module("replay_trade_ready_cases")
    report = module.audit_trade_ready_replays(tmp_path)
    assert report["status"] == "NO_TRADE_PLAN_READY_FOUND"
    assert report["validated_trade_ready_count"] == 0
    assert report["edge_claim_allowed"] is False


def test_live_harness_recognizes_forex_without_routing_to_xau_proxy():
    module = _tool_module("run_live_ai_smc_full_system")
    assert module.normalize_symbol("EUR/NZD") == "EURNZD"
    assert module.is_forex_pair("EURNZD") is True
    assert module.is_forex_pair("AVAXUSDT") is False


def test_forex_live_loader_reconstructs_closed_ny_daily_from_hourly(monkeypatch):
    module = _tool_module("run_live_ai_smc_full_system")
    calls: list[str] = []

    def fake_yahoo(_ticker: str, *, interval: str, range_: str) -> pd.DataFrame:
        calls.append(interval)
        if interval == "15m":
            return _df(120, "15min", base=0.81)
        if interval == "1h":
            return _df(900, "1h", base=0.81)
        raise AssertionError(f"Standalone Yahoo interval must not be requested: {interval}/{range_}")

    monkeypatch.setattr(module, "yahoo_chart_df", fake_yahoo)
    frames, manifest = module.load_yahoo_forex_timeframes("USDCHF")

    assert calls == ["15m", "1h"]
    assert not frames["1d"].empty
    assert set(frames["1d"].columns) == {"timestamp", "open", "high", "low", "close", "volume"}
    assert (frames["1d"]["high"] >= frames["1d"][["open", "close", "low"]].max(axis=1)).all()
    assert (frames["1d"]["low"] <= frames["1d"][["open", "close", "high"]].min(axis=1)).all()
    assert manifest["daily_session_profile"] == "new_york_close_daily"
    assert manifest["timeframes"]["1d"]["derived_from"] == "yahoo_chart_1h"


def test_live_conservative_provider_does_not_let_active_range_override_htf_bias():
    module = _tool_module("run_live_ai_smc_full_system")

    class Request:
        evidence_pack = {
            "symbol": "EURNZD",
            "ohlcv_summaries": {
                "15m": {"first_open": 1.0, "last_close": 1.01, "high": 1.03, "low": 0.99},
                "1h": {"first_open": 1.0, "last_close": 1.2, "high": 1.25, "low": 0.98},
                "4h": {"first_open": 1.0, "last_close": 1.2, "high": 1.25, "low": 0.98},
                "1d": {"first_open": 1.0, "last_close": 1.2, "high": 1.25, "low": 0.98},
            },
            "active_range_authority": {
                "selected_range": {
                    "status": "RESOLVED_ACTIVE_RANGE",
                    "timeframe": "4h",
                    "direction": "bearish",
                    "range_high": 1.25,
                    "range_low": 1.0,
                    "equilibrium": 1.125,
                    "price_location": "premium",
                    "range_id": "range1",
                    "protected_high": 1.25,
                    "protected_low": 1.0,
                    "width_atr": 2.0,
                    "max_width_atr": 22.0,
                    "protected_high_pivot_id": "h1",
                    "protected_low_pivot_id": "l1",
                    "authority_notes": ["Range map is bearish."],
                }
            },
        }

    payload = module.build_conservative_ai_payload(Request(), {"source": "test"})
    assert payload["direction"] == "bullish"
    assert payload["bias_summary"]["final_bias"] == "bullish"
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(decision, {"detector_candidates": {}, "active_range_authority": Request.evidence_pack["active_range_authority"]})
    assert result.status == "VALIDATED"
    assert any(issue.code == "direction_conflicts_with_active_range" and issue.severity == "warning" for issue in result.issues)


def test_live_provider_downgrades_direction_when_causal_replay_disagrees():
    module = _tool_module("run_live_ai_smc_full_system")

    class Request:
        evidence_pack = {
            "symbol": "EURJPY",
            "ohlcv_summaries": {
                timeframe: {"first_open": 185.0, "last_close": 182.0, "high": 188.0, "low": 179.0}
                for timeframe in ("15m", "1h", "4h", "1d")
            },
            "active_range_authority": {"selected_range": None},
            "formal_causal_episode_graph": {
                "schema": "formal_causal_episode_graph_v2",
                "authority_contract": {"enforcement_ready": True},
                "invariants": {
                    "status": "REVIEW_REQUIRED",
                    "violations": ["1d_v1_controlling_external_break_survives_v3"],
                },
                "current_story": {},
            },
        }

    payload = module.build_conservative_ai_payload(Request(), {"source": "test"})

    assert payload["official_state"] == "REVIEW_REQUIRED"
    assert payload["direction"] == "mixed"
    assert payload["bias_summary"]["final_bias"] == "mixed"
    assert payload["active_poi"]["poi_id"] is None


def test_live_provider_does_not_deny_fresh_v3_displacement_in_final_thesis():
    module = _tool_module("run_live_ai_smc_full_system")

    class Request:
        evidence_pack = {
            "symbol": "HYPEUSDT",
            "ohlcv_summaries": {
                timeframe: {
                    "first_open": 55.0,
                    "last_close": 56.0,
                    "high": 58.0,
                    "low": 53.0,
                }
                for timeframe in ("15m", "1h", "4h", "1d")
            },
            "detector_candidates": {},
            "active_range_authority": {"selected_range": None},
            "structure_engine_v3_shadow": {
                "decision_time": "2026-08-14T09:00:00Z",
                "timeframes": {
                    "15m": {
                        "latest_accepted_external": {
                            "accepted_for_shadow_story": True,
                            "source_break_object_id": "hype:15m:mss:bearish",
                            "event_type": "EXTERNAL_MSS_CONFIRMED_BEARISH",
                            "direction": "bearish",
                            "confirmation_time": "2026-08-14T07:30:00Z",
                            "displacement_score": 0.90,
                        }
                    }
                },
            },
        }

    payload = module.build_conservative_ai_payload(Request(), {"source": "test"})

    assert payload["displacement_assessment"]["structure_broken"] is True
    assert "fresh V3-accepted 15m EXTERNAL_MSS_CONFIRMED_BEARISH exists" in payload["final_thesis"]
    assert "does not have validated sweep/displacement" not in payload["final_thesis"]
    assert "fresh V3-accepted 15m displacement" in payload["liquidity_story"]["narrative"]


def test_live_provider_preserves_bullish_external_structure_with_internal_pullback():
    module = _tool_module("run_live_ai_smc_full_system")

    class Request:
        evidence_pack = {
            "symbol": "SUIUSDT",
            "ohlcv_summaries": {
                "15m": {"first_open": 0.80, "last_close": 0.7309, "high": 0.8109, "low": 0.6503},
                "1h": {"first_open": 1.10, "last_close": 0.7323, "high": 1.1324, "low": 0.6503},
                "4h": {"first_open": 0.93, "last_close": 0.7364, "high": 1.4140, "low": 0.6503},
                "1d": {"first_open": 2.67, "last_close": 0.7152, "high": 4.4478, "low": 0.5669},
            },
            "detector_candidates": {
                "15m": {
                    "structure_breaks": [
                        {
                            "object_id": "sui:15m:external_bos_up",
                            "direction": "bullish",
                            "confirmed_at": "2026-07-02T13:45:00+00:00",
                            "price": 0.7474,
                            "structure_scope": "external",
                            "evidence": {"structure_scope": "external"},
                        },
                        {
                            "object_id": "sui:15m:internal_choch_down",
                            "direction": "bearish",
                            "confirmed_at": "2026-07-02T22:45:00+00:00",
                            "price": 0.7334,
                            "structure_scope": "internal",
                            "evidence": {"structure_scope": "internal"},
                        },
                    ]
                },
                "1h": {
                    "structure_breaks": [
                        {
                            "object_id": "sui:1h:external_bos_up",
                            "direction": "bullish",
                            "confirmed_at": "2026-07-02T14:00:00+00:00",
                            "price": 0.7401,
                            "structure_scope": "external",
                            "evidence": {"structure_scope": "external"},
                        },
                        {
                            "object_id": "sui:1h:internal_choch_down",
                            "direction": "bearish",
                            "confirmed_at": "2026-07-02T23:00:00+00:00",
                            "price": 0.7334,
                            "structure_scope": "internal",
                            "evidence": {"structure_scope": "internal"},
                        },
                    ]
                },
                "4h": {
                    "structure_breaks": [
                        {
                            "object_id": "sui:4h:external_bos_up",
                            "direction": "bullish",
                            "confirmed_at": "2026-07-02T12:00:00+00:00",
                            "price": 0.7401,
                            "structure_scope": "external",
                            "evidence": {"structure_scope": "external"},
                        }
                    ]
                },
                "1d": {"structure_breaks": []},
            },
            "active_range_authority": {
                "selected_range": {
                    "status": "RESOLVED_ACTIVE_RANGE",
                    "timeframe": "1h",
                    "direction": "bearish",
                    "range_high": 0.7532,
                    "range_low": 0.6503,
                    "equilibrium": 0.70175,
                    "price_location": "premium",
                    "range_id": "sui:1h:test_range",
                    "protected_high": 0.7532,
                    "protected_low": 0.6503,
                    "width_atr": 8.0,
                    "max_width_atr": 22.0,
                    "protected_high_pivot_id": "sui:h",
                    "protected_low_pivot_id": "sui:l",
                    "authority_notes": ["Range map is bearish but must not override HTF structure consensus."],
                }
            },
        }

    payload = module.build_conservative_ai_payload(Request(), {"source": "test"})

    assert payload["bias_summary"]["1h"] == "bullish_external_bearish_internal_pullback"
    assert payload["bias_summary"]["final_bias"] == "mixed"
    assert payload["direction"] == "mixed"
    assert payload["official_state"] == "THESIS_ONLY"
    assert any(
        "1h: raw summary bias bearish conflicts with confirmed structure vote bullish" in line
        for line in payload["bias_summary"]["evidence"]
    )
    assert any(
        "treat as pullback, not full bias flip" in line
        for line in payload["bias_summary"]["evidence"]
    )
    decision = parse_ai_smc_decision(payload)
    result = validate_ai_smc_decision(
        decision,
        {"detector_candidates": Request.evidence_pack["detector_candidates"], "active_range_authority": Request.evidence_pack["active_range_authority"]},
    )
    assert result.status == "VALIDATED"


def test_forex_perception_accepts_weekend_closure_without_discarding_context():
    before_gap = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-26 20:00", periods=4, freq="15min", tz="UTC"),
            "open": [1.0, 1.01, 1.02, 1.03],
            "high": [1.02, 1.03, 1.04, 1.05],
            "low": [0.99, 1.0, 1.01, 1.02],
            "close": [1.01, 1.02, 1.03, 1.04],
            "volume": [100, 101, 102, 103],
        }
    )
    after_gap = _df(60, "15min", base=1.05)
    after_gap["timestamp"] = pd.date_range("2026-06-28 21:00", periods=len(after_gap), freq="15min", tz="UTC")
    gapped = pd.concat([before_gap, after_gap], ignore_index=True)

    _, forex_report = _run_perception_candidates(symbol="EURNZD", timeframe_dfs={"15m": gapped})
    assert forex_report["timeframes"]["15m"]["status"] == "PASS"
    assert forex_report["timeframes"]["15m"]["session_profile"] == "forex_5d"
    assert forex_report["timeframes"]["15m"]["session_gap_trimmed"] is False
    assert forex_report["timeframes"]["15m"]["rows_analyzed"] == len(gapped)

    _, gold_report = _run_perception_candidates(symbol="XAUUSD", timeframe_dfs={"15m": gapped})
    assert gold_report["timeframes"]["15m"]["status"] == "PASS"
    assert gold_report["timeframes"]["15m"]["session_profile"] == "forex_5d"
    assert gold_report["timeframes"]["15m"]["session_gap_trimmed"] is False
    assert gold_report["timeframes"]["15m"]["rows_analyzed"] == len(gapped)

    _, crypto_report = _run_perception_candidates(symbol="AVAXUSDT", timeframe_dfs={"15m": gapped})
    assert crypto_report["timeframes"]["15m"]["status"] == "FAILED"


def test_forex_perception_still_rejects_a_midweek_data_hole() -> None:
    first = _df(20, "15min", base=1.05)
    first["timestamp"] = pd.date_range(
        "2026-06-23 08:00", periods=len(first), freq="15min", tz="UTC"
    )
    second = _df(20, "15min", base=1.06)
    second["timestamp"] = pd.date_range(
        "2026-06-23 14:00", periods=len(second), freq="15min", tz="UTC"
    )
    gapped = pd.concat([first, second], ignore_index=True)

    _, report = _run_perception_candidates(
        symbol="EURNZD",
        timeframe_dfs={"15m": gapped},
    )

    assert report["timeframes"]["15m"]["status"] == "FAILED"
    assert "gaps" in report["timeframes"]["15m"]["error"].lower()


def test_forex_perception_uses_long_clean_segment_after_old_midweek_hole() -> None:
    first = _df(30, "1h", base=1.05)
    first["timestamp"] = pd.date_range(
        "2026-01-06 00:00", periods=len(first), freq="1h", tz="UTC"
    )
    second = _df(520, "1h", base=1.06)
    second["timestamp"] = pd.date_range(
        "2026-01-07 10:00", periods=len(second), freq="1h", tz="UTC"
    )
    gapped = pd.concat([first, second], ignore_index=True)

    candidates, report = _run_perception_candidates(
        symbol="EURJPY",
        timeframe_dfs={"1h": gapped},
    )

    tf_report = report["timeframes"]["1h"]
    assert tf_report["status"] == "PASS"
    assert tf_report["session_gap_trimmed"] is True
    assert tf_report["original_rows"] == 550
    assert tf_report["rows_analyzed"] == 520
    assert candidates["1h"]


def test_effective_depth_uses_post_gap_rows_and_failed_perception_is_zero() -> None:
    raw = {
        "4h": {
            "timeframe": "4h",
            "row_count": 3721,
            "minimum_required": 500,
            "status": "PASS",
            "context_depth_warning": False,
            "authority_adjustment": "normal",
        },
        "1h": {
            "timeframe": "1h",
            "row_count": 1300,
            "minimum_required": 1000,
            "status": "PASS",
            "context_depth_warning": False,
            "authority_adjustment": "normal",
        },
    }
    report = _effective_context_depth_report(
        raw,
        perception_report={
            "timeframes": {
                "4h": {"status": "PASS", "rows_analyzed": 349},
                "1h": {"status": "FAILED", "error": "gap"},
            }
        },
        minimum_depths={"4h": 500, "1h": 1000},
    )

    assert report["4h"]["raw_row_count"] == 3721
    assert report["4h"]["row_count"] == 349
    assert report["4h"]["context_depth_warning"] is True
    assert report["1h"]["row_count"] == 0
    assert report["1h"]["status"] == "SHALLOW_CONTEXT"


def test_data_failed_timeframe_candidates_are_suppressed_before_poi_enrichment() -> None:
    candidates, suppressed = _suppress_blocked_definition_timeframes(
        {"4h": {"structure_breaks": [{"object_id": "bad-break"}]}, "1d": {"swings": []}},
        definition_conformance={
            "by_timeframe": {
                "4h": {
                    "certificate": {
                        "status": "DATA_FAILED",
                        "failures": ["unexplained candle gap"],
                    }
                },
                "1d": {"certificate": {"status": "BOUNDARY_SENSITIVE", "failures": []}},
            }
        },
    )

    assert candidates["4h"] == {}
    assert candidates["1d"] == {"swings": []}
    assert suppressed["4h"]["status"] == "DATA_FAILED"
    assert "unexplained candle gap" in suppressed["4h"]["reason"]


def test_forex_daily_session_accepts_bounded_holiday_closures() -> None:
    timestamps = list(pd.bdate_range("2025-11-03", periods=80, tz="UTC"))
    timestamps = [timestamp for timestamp in timestamps if timestamp.date().isoformat() != "2025-12-25"]
    df = _df(len(timestamps), "1d", base=182.0)
    df["timestamp"] = timestamps

    candidates, report = _run_perception_candidates(
        symbol="EURJPY",
        timeframe_dfs={"1d": df},
    )

    assert report["timeframes"]["1d"]["status"] == "PASS"
    assert report["timeframes"]["1d"]["session_gap_trimmed"] is False
    assert candidates["1d"]


def test_thesis_cannot_claim_alignment_when_causal_replay_requires_review() -> None:
    evidence_pack = {
        "formal_structure_graph": {
            "narrative_context": {
                "state": "ALIGNED_CONTINUATION",
                "context_timeframe": "1d",
                "context_bias": "bearish",
                "is_coherent": True,
                "sentence": "All context timeframes align bearish.",
                "draw": {"target_price": 179.0, "direction": "bearish"},
            }
        },
        "formal_causal_episode_graph": {
            "authority_contract": {"enforcement_ready": True},
            "invariants": {
                "status": "REVIEW_REQUIRED",
                "violations": ["1d_v1_controlling_external_break_survives_v3"],
            },
        },
    }

    narrative = _narrative_context(evidence_pack)

    assert narrative["state"] == "RECONCILIATION_REQUIRED"
    assert narrative["context_bias"] == "unresolved"
    assert narrative["is_coherent"] is False
    assert narrative["draw"] == {}
    assert "provisionally reads bearish" in narrative["sentence"]
