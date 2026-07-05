from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import AISMCTraderBrain, REASONING_ORDER, parse_ai_smc_decision
from smc_desk.brain.smc_evidence_pack_builder import assert_evidence_pack_has_no_decision, build_smc_evidence_pack
from smc_desk.colleague.smc_thesis_ai_v1 import build_smc_thesis_ai_v1
from smc_desk.rendering.smc_trader_annotation_renderer import (
    DEBUG_CHART_LABEL,
    build_debug_annotation_scene,
    build_smc_trader_annotation_scene,
    render_smc_trader_annotation_chart,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-29 10:00", periods=20, freq="15min", tz="UTC"),
            "open": [100 + (i % 3) * 0.1 for i in range(20)],
            "high": [101 + (i % 4) * 0.1 for i in range(20)],
            "low": [99 - (i % 2) * 0.1 for i in range(20)],
            "close": [100.2 - (i % 3) * 0.1 for i in range(20)],
            "volume": [1000 + i for i in range(20)],
        }
    )


def _pack(tmp_path=None):
    chart_images = {}
    if tmp_path is not None:
        image_path = tmp_path / "BTCUSDT_15m_clean.png"
        image_path.write_bytes(b"png")
        chart_images = {"15m": image_path}
    pack = build_smc_evidence_pack(
        symbol="BTCUSDT",
        timeframe_dfs={"15m": _df()},
        chart_images=chart_images,
        detector_candidates={
            "15m": {
                "sweeps": [{"object_id": "sweep1", "side": "buy_side", "price": 102.0, "direction": "bearish"}],
                "structure_breaks": [{"object_id": "break1", "direction": "bearish", "price": 98.0}],
                "fvgs": [{"object_id": "fvg1", "direction": "bearish", "price_low": 99.6, "price_high": 100.4}],
                "order_blocks": [{"object_id": "poi1", "direction": "bearish", "price_low": 100.0, "price_high": 101.0}],
                "liquidity_levels": [{"object_id": "liq1", "side": "sell_side", "price": 95.0}],
            }
        },
    )
    pack["active_range_authority"] = {
        "schema": "active_range_authority_v1",
        "symbol": "BTCUSDT",
        "status": "RESOLVED_ACTIVE_RANGE",
        "method": "test_fixture_structural_range",
        "selected_range": {
            "status": "RESOLVED_ACTIVE_RANGE",
            "timeframe": "1h",
            "direction": "bearish",
            "range_high": 103.0,
            "range_low": 95.0,
            "equilibrium": 99.0,
            "price_location": "premium",
            "source": "protected_swing_pair",
            "range_id": "test:range1",
            "protected_high": 103.0,
            "protected_low": 95.0,
            "width_atr": 8.0,
            "max_width_atr": 24.0,
        },
    }
    from smc_desk.perception.formal_structure_graph import build_mtf_structure_graph
    pack["formal_structure_graph"] = build_mtf_structure_graph(
        symbol="BTCUSDT",
        detector_candidates=pack.get("detector_candidates", pack.get("detector_candidates", {})),
        active_range_authority=pack["active_range_authority"],
        timeframe_dfs={"15m": _df(), "1h": _df(), "4h": _df(), "1d": _df()},
    )
    return pack


def _valid_payload():
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY",
        "setup_grade": "A",
        "direction": "bearish",
        "setup_model": "buy_side_sweep_to_bearish_continuation",
        "bias_summary": {
            "daily": "bearish corrective structure",
            "4h": "bearish below premium supply",
            "1h": "bearish after buy-side raid",
            "final_bias": "bearish",
            "evidence": ["1h lower high", "15m displacement"],
        },
        "active_range": {
            "timeframe": "1h",
            "high": 103.0,
            "low": 95.0,
            "equilibrium": 99.0,
            "price_location": "premium",
            "source": "protected_swing_pair",
            "range_id": "test:range1",
            "protected_high": 103.0,
            "protected_low": 95.0,
            "width_atr": 8.0,
            "max_allowed_width_atr": 24.0,
            "evidence_object_ids": ["test_high", "test_low"],
            "evidence": ["range1"],
        },
        "liquidity_story": {
            "obvious_liquidity": [{"liquidity_id": "bsl1", "side": "buy_side", "price": 102.0, "label": "equal highs"}],
            "swept_liquidity": [{"liquidity_id": "sweep1", "side": "buy_side", "price": 102.0, "label": "buy-side sweep", "evidence_object_ids": ["sweep1"]}],
            "unswept_liquidity": [{"liquidity_id": "liq1", "side": "sell_side", "price": 95.0, "label": "range low", "evidence_object_ids": ["liq1"]}],
            "narrative": "Buy-side liquidity was swept before bearish displacement; sell-side liquidity is the model-completion draw.",
        },
        "displacement_assessment": {
            "direction": "bearish",
            "quality": "clean",
            "structure_broken": True,
            "evidence_object_ids": ["break1"],
            "summary": "Clean bearish displacement after the sweep.",
        },
        "active_poi": {
            "poi_id": "poi1",
            "timeframe": "15m",
            "kind": "supply_order_block",
            "direction": "bearish",
            "price_low": 100.0,
            "price_high": 101.0,
            "freshness": "fresh",
            "evidence_object_ids": ["poi1"],
            "summary": "Fresh bearish supply that caused displacement.",
        },
        "entry_plan": {
            "entry_ready": True,
            "entry_timeframe": "15m",
            "refinement_timeframe": "5m",
            "entry_price": 100.5,
            "mapped_entry_price": 100.5,
            "entry_zone_low": 100.0,
            "entry_zone_high": 101.0,
            "entry_anchor": "poi1",
            "signal_type": "15m supply rejection",
            "required_confirmation": ["reject supply", "hold below invalidation"],
            "evidence_object_ids": ["poi1"],
            "summary": "Entry is ready only because price rejected the active POI.",
        },
        "stop_loss_plan": {
            "stop_price": 102.0,
            "mapped_stop_price": 102.0,
            "stop_anchor": "above_sweep_high",
            "structural_invalidation_price": 102.0,
            "source": "above supply high",
            "buffer_notes": "above protected supply high",
            "evidence_object_ids": ["sweep1"],
            "summary": "Stop equals structural invalidation above the supply zone.",
        },
        "target_plan": {
            "targets": [{"price": 95.0, "mapped_target_price": 95.0, "target_anchor": "liq1", "label": "TP1", "timeframe": "1h", "reason": "sell-side model-completion liquidity", "evidence_object_ids": ["liq1"]}],
            "model_completion_liquidity_id": "liq1",
            "summary": "Target is the 1h sell-side liquidity draw.",
        },
        "rr_status": {"rr": 3.3333, "minimum_rr": 3.0, "pass_rr": True, "notes": "Reward/risk clears 3R."},
        "invalidation": {"invalidation_price": 102.0, "mapped_invalidation_price": 102.0, "invalidation_anchor": "above_sweep_high", "condition": "Acceptance above supply invalidates bearish plan.", "source": "supply_high", "evidence_object_ids": ["sweep1"]},
        "annotation_plan": {
            "chart_template": "trade_plan_chart",
            "show_trade_box": True,
            "labels": [
                {"text": "1H bearish context", "kind": "context", "timeframe": "1h"},
                {"text": "Buy-side sweep", "kind": "sweep", "price": 102.0},
                {"text": "Bearish displacement", "kind": "displacement", "price": 98.0},
                {"text": "Active supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
                {"text": "Trade plan ready", "kind": "state"},
            ],
            "levels": [
                {"label": "Active supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
                {"label": "Entry", "kind": "entry", "price": 100.0},
                {"label": "SL", "kind": "stop", "price": 101.5},
                {"label": "TP1", "kind": "target", "price": 95.0},
            ],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "passed",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [],
            "remaining_uncertainties": [],
        },
        "final_thesis": "Bearish trade plan is ready only after sweep, displacement, active supply rejection, structural invalidation, and 3R target validation.",
    }


def _watch_payload():
    payload = _valid_payload()
    payload["official_state"] = "WAIT_FOR_RETRACE_TO_SUPPLY"
    payload["setup_grade"] = "B"
    payload["entry_plan"]["entry_ready"] = False
    payload["entry_plan"]["entry_price"] = None
    payload["stop_loss_plan"]["stop_price"] = None
    payload["target_plan"]["targets"] = []
    payload["target_plan"]["model_completion_liquidity_id"] = None
    payload["rr_status"] = {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "RR not available until a real entry exists."}
    payload["annotation_plan"]["chart_template"] = "watch_chart"
    payload["annotation_plan"]["show_trade_box"] = False
    payload["annotation_plan"]["levels"] = [
        {"label": "Active supply watch", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
        {"label": "Invalidation, not SL", "kind": "invalidation", "price": 101.5},
    ]
    payload["final_thesis"] = "Bearish watch only; wait for retrace and confirmation before any trade levels exist."
    return payload


def _decision(payload=None):
    return parse_ai_smc_decision(payload or _valid_payload())


def _issue_codes(result):
    return {issue.code for issue in result.issues}


def test_evidence_pack_builder_does_not_decide():
    pack = _pack()
    assert_evidence_pack_has_no_decision(pack)
    assert pack["authority_contract"]["signal_allowed"] is False
    assert "official_state" not in pack


def test_detector_outputs_are_candidates_only():
    pack = _pack()
    for tf_payload in pack["detector_candidates"].values():
        for items in tf_payload.values():
            for item in items:
                assert item["candidate_role"] == "candidate_only"
                assert item["official_decision_authority"] is False


def test_ai_trader_brain_receives_images_and_structured_data(tmp_path):
    pack = _pack(tmp_path)

    def completion(prompt: str):
        assert "chart_images" in prompt
        assert "ohlcv_summaries" in prompt
        assert "BTCUSDT_15m_clean.png" in prompt
        return json.dumps(_valid_payload())

    decision = AISMCTraderBrain(completion).decide(pack)
    assert decision.symbol == "BTCUSDT"


def test_ai_reasoning_order_is_enforced():
    payload = _valid_payload()
    payload["annotation_plan"]["reasoning_order"] = list(reversed(REASONING_ORDER))
    with pytest.raises(ValueError, match="reasoning order"):
        parse_ai_smc_decision(payload)


def test_ai_output_schema_valid():
    decision = _decision()
    dumped = decision.model_dump(mode="json", by_alias=True)
    for field in (
        "official_state",
        "setup_grade",
        "direction",
        "setup_model",
        "bias_summary",
        "active_range",
        "liquidity_story",
        "displacement_assessment",
        "active_poi",
        "entry_plan",
        "stop_loss_plan",
        "target_plan",
        "rr_status",
        "invalidation",
        "annotation_plan",
        "final_thesis",
    ):
        assert field in dumped


def test_ai_claimed_liquidity_sweep_must_validate():
    pack = _pack()
    pack["detector_candidates"]["15m"]["sweeps"] = []
    result = validate_ai_smc_decision(_decision(), pack)
    assert result.status == "REVIEW_REQUIRED"
    assert "sweep_claim_without_candidate" in _issue_codes(result)


def test_ai_claimed_displacement_must_validate():
    pack = _pack()
    pack["detector_candidates"]["15m"]["structure_breaks"] = []
    pack["detector_candidates"]["15m"]["fvgs"] = []
    pack["detector_candidates"]["15m"]["poi_grade_fvgs"] = []
    result = validate_ai_smc_decision(_decision(), pack)
    assert result.status == "REVIEW_REQUIRED"
    assert "displacement_without_candidate" in _issue_codes(result)


def test_trade_ready_requires_real_displacement_and_non_watch_thesis():
    payload = _valid_payload()
    payload["displacement_assessment"] = {
        "direction": "none",
        "quality": "none",
        "structure_broken": False,
        "evidence_object_ids": [],
        "summary": "No validated displacement candidate was promoted.",
    }
    payload["final_thesis"] = (
        "BTCUSDT: WATCH_ONLY. Directional context is bearish, but the system "
        "does not have validated sweep/displacement/active POI/entry evidence, "
        "so it refuses a trade plan."
    )

    result = validate_ai_smc_decision(_decision(payload), _pack())

    assert result.status == "REVIEW_REQUIRED"
    assert "trade_ready_requires_valid_displacement" in _issue_codes(result)
    assert "trade_ready_thesis_contradiction" in _issue_codes(result)
    assert result.official_decision["official_state"] == "REVIEW_REQUIRED"
    assert result.official_decision["entry_plan"]["entry_price"] is None
    assert result.official_decision["stop_loss_plan"]["stop_price"] is None
    assert result.official_decision["target_plan"]["targets"] == []
    assert result.official_decision["annotation_plan"]["show_trade_box"] is False


def test_no_validated_sweep_or_displacement_cannot_be_trade_plan_ready():
    payload = _valid_payload()
    payload["liquidity_story"]["swept_liquidity"] = []
    payload["displacement_assessment"] = {
        "direction": "none",
        "quality": "none",
        "structure_broken": False,
        "evidence_object_ids": [],
        "summary": "No validated sweep or displacement promoted.",
    }
    payload["annotation_plan"]["labels"].append(
        {"text": "Watch only - wait for real POI confirmation", "kind": "state"}
    )
    payload["final_thesis"] = "Watch only because no validated sweep or displacement was promoted."

    result = validate_ai_smc_decision(_decision(payload), _pack())

    assert result.status == "REVIEW_REQUIRED"
    assert "trade_ready_requires_valid_displacement" in _issue_codes(result)
    assert "trade_ready_annotation_contradiction" in _issue_codes(result)
    assert result.official_decision["annotation_plan"]["chart_template"] == "review_chart"
    assert result.official_decision["annotation_plan"]["show_trade_box"] is False


def test_renderer_state_text_and_trade_box_are_consistent():
    payload = _valid_payload()
    payload["annotation_plan"]["labels"] = [
        {"text": "No validated sweep or displacement promoted", "kind": "state"},
        {"text": "Watch only - wait for real POI confirmation", "kind": "state"},
    ]

    result = validate_ai_smc_decision(_decision(payload), _pack())

    assert result.status == "REVIEW_REQUIRED"
    assert "trade_ready_annotation_contradiction" in _issue_codes(result)
    assert result.official_decision["official_state"] == "REVIEW_REQUIRED"
    assert result.official_decision["entry_plan"]["entry_price"] is None
    assert result.official_decision["stop_loss_plan"]["stop_price"] is None
    assert result.official_decision["target_plan"]["targets"] == []
    assert result.official_decision["annotation_plan"]["show_trade_box"] is False


def test_ai_target_must_be_model_completion_liquidity():
    payload = _valid_payload()
    payload["target_plan"]["targets"][0]["price"] = 94.0
    payload["target_plan"]["targets"][0]["evidence_object_ids"] = []
    payload["rr_status"]["rr"] = 4.0
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "target_not_model_completion_liquidity" in _issue_codes(result)


def test_ai_target_conflicting_with_model_rejected():
    payload = _valid_payload()
    payload["target_plan"]["targets"][0]["price"] = 103.0
    payload["rr_status"]["rr"] = 2.0
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "bearish_target_above_entry" in _issue_codes(result)


def test_ai_sl_must_equal_structural_invalidation():
    payload = _valid_payload()
    payload["stop_loss_plan"]["stop_price"] = 101.2
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "stop_not_structural_invalidation" in _issue_codes(result)


def test_rr_must_be_at_least_three_for_trade_ready():
    payload = _valid_payload()
    payload["target_plan"]["targets"][0]["price"] = 96.5
    payload["rr_status"]["rr"] = 2.333
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "rr_below_minimum" in _issue_codes(result)


def test_watch_chart_has_no_trade_box():
    result = validate_ai_smc_decision(_decision(_watch_payload()), _pack())
    assert result.status == "VALIDATED"
    assert result.official_decision["annotation_plan"]["show_trade_box"] is False
    assert result.official_decision["entry_plan"]["entry_price"] is None
    assert result.official_decision["stop_loss_plan"]["stop_price"] is None
    assert result.official_decision["target_plan"]["targets"] == []


def test_trade_chart_has_entry_sl_tp_rr_only_when_ready():
    result = validate_ai_smc_decision(_decision(), _pack())
    assert result.status == "VALIDATED"
    scene = build_smc_trader_annotation_scene(result)
    kinds = {level["kind"] for level in scene["levels"]}
    assert {"entry", "stop", "target"}.issubset(kinds)
    assert result.official_decision["official_state"] == "TRADE_PLAN_READY"


def test_official_renderer_uses_validated_ai_annotation_plan(tmp_path):
    result = validate_ai_smc_decision(_decision(), _pack())
    output_path = tmp_path / "official.png"
    scene = render_smc_trader_annotation_chart(_df(), result, output_path)
    assert output_path.exists()
    assert scene["source"] == "ValidatedAISMCDecision"
    assert scene["labels"] == result.official_decision["annotation_plan"]["labels"]


def test_debug_chart_is_separate():
    scene = build_debug_annotation_scene({"raw_bos": ["debug"]})
    assert scene["official"] is False
    assert scene["banner"] == DEBUG_CHART_LABEL


def test_clean_annotation_max_label_count():
    payload = _watch_payload()
    payload["annotation_plan"]["labels"] = [
        {"text": f"Label {idx}", "kind": "context"} for idx in range(8)
    ]
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "annotation_label_budget_exceeded" in _issue_codes(result)


def test_watch_annotation_scene_is_sparse_trader_markup():
    payload = _watch_payload()
    payload["annotation_plan"]["labels"] = [
        {"text": "HTF context", "kind": "context"},
        {"text": "Buy-side sweep", "kind": "sweep", "price": 102.0},
        {"text": "Bearish displacement", "kind": "displacement", "price": 98.0},
        {"text": "Active supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
        {"text": "Wait for confirmation", "kind": "state"},
    ]
    payload["annotation_plan"]["levels"] = [
        {"label": "Active supply", "kind": "poi", "price_low": 100.0, "price_high": 101.0},
        {"label": "Invalidation", "kind": "invalidation", "price": 101.5},
        {"label": "First draw", "kind": "liquidity", "price": 95.0},
        {"label": "Second draw", "kind": "liquidity", "price": 94.0},
    ]

    result = validate_ai_smc_decision(_decision(payload), _pack())
    scene = build_smc_trader_annotation_scene(result)

    assert result.status == "VALIDATED"
    assert scene["display_contract"] == "trader_markup_sparse"
    assert len(scene["labels"]) == 5
    assert len(scene["visible_labels"]) == 3
    assert len(scene["visible_levels"]) == 3
    assert scene["hidden_label_count"] == 2
    assert scene["hidden_level_count"] == 1


def test_annotation_plan_supports_local_structure_geometry(tmp_path):
    payload = _watch_payload()
    payload["annotation_plan"]["labels"] = [
        {"text": "BOS", "kind": "bos", "price": 102.0},
        {"text": "IDM", "kind": "idm", "price": 99.0},
        {"text": "Bullish OB", "kind": "order_block", "price_low": 99.4, "price_high": 100.2},
    ]
    payload["annotation_plan"]["levels"] = [
        {"label": "BOS", "kind": "bos", "price": 102.0, "start_index": 5, "end_index": 11},
        {"label": "IDM", "kind": "idm", "price": 99.0, "start_index": 8, "end_index": 15, "line_style": "dotted"},
        {"label": "OB", "kind": "order_block", "price_low": 99.4, "price_high": 100.2, "start_index": 12, "end_index": 18},
    ]

    result = validate_ai_smc_decision(_decision(payload), _pack())
    output_path = tmp_path / "local_geometry.png"
    scene = render_smc_trader_annotation_chart(_df(), result, output_path)

    assert result.status == "VALIDATED"
    assert output_path.exists()
    assert scene["display_contract"] == "trader_markup_sparse"
    visible = {level["label"]: level for level in scene["visible_levels"]}
    assert visible["BOS"]["start_index"] == 5
    assert visible["BOS"]["end_index"] == 11
    assert visible["IDM"]["line_style"] == "dotted"
    assert visible["OB"]["kind"] == "order_block"


def test_no_1m_official_entry():
    payload = _valid_payload()
    payload["entry_plan"]["entry_timeframe"] = "1m"
    result = validate_ai_smc_decision(_decision(payload), _pack())
    assert result.status == "REVIEW_REQUIRED"
    assert "forbidden_1m_entry" in _issue_codes(result)


def test_ai_smc_thesis_uses_validated_boundary():
    result = validate_ai_smc_decision(_decision(_watch_payload()), _pack())
    thesis = build_smc_thesis_ai_v1(validation_result=result, evidence_pack=_pack())
    assert thesis["source"] == "ValidatedAISMCDecision"
    assert thesis["show_trade_box"] is False
    assert thesis["claim_sequence"][0] == "bias_summary"
