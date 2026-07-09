from __future__ import annotations

import json

from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision
from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, parse_ai_smc_decision
from smc_desk.perception.formal_structure_graph import (
    build_mtf_structure_graph,
    graph_requires_thesis_only,
    graph_requires_mixed_bias,
    graph_thesis_sentence,
    graph_invariant_violation_codes,
)


# ── Fixtures ────────────────────────────────────────────────────────────


def _break(obj_id: str, direction: str, confirmed_at: str, scope: str, broken_price: float, **kw) -> dict:
    d = {
        "object_id": obj_id,
        "object_type": "structure_break",
        "break_type": "BOS",
        "direction": direction,
        "confirmed_at": confirmed_at,
        "structure_scope": scope,
        "price_low": broken_price - 1.0,
        "price_high": broken_price + 1.0,
        "evidence": {
            "structure_scope": scope,
            "broken_price": str(broken_price),
            "body_close_penetration": str(kw.get("body_close_penetration", 0.0)),
            "is_unconfirmed_probe": kw.get("is_unconfirmed_probe", False),
            "broke_protected_swing": kw.get("broke_protected_swing", False),
        },
    }
    if kw.get("is_choch"):
        d["is_choch"] = True
        d["break_type"] = "CHoCH"
    return d


def _default_detector_candidates() -> dict[str, Any]:
    return {
        "1d": {
            "structure_breaks": [
                _break("1d_bearish_choch", "bearish", "2026-06-25T00:00:00Z", "external", 62232.0, is_choch=True, broke_protected_swing=True),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
        "4h": {
            "structure_breaks": [
                _break("4h_bullish_choch", "bullish", "2026-07-02T04:00:00Z", "external", 60758.0, is_choch=True, broke_protected_swing=True),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
        "1h": {
            "structure_breaks": [
                _break("1h_bullish_bos", "bullish", "2026-07-02T12:00:00Z", "external", 61322.0),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
        "15m": {
            "structure_breaks": [
                _break("15m_bullish_bos", "bullish", "2026-07-03T08:45:00Z", "external", 61825.0),
                _break("15m_bearish_internal", "bearish", "2026-07-03T09:00:00Z", "internal", 61612.0, is_choch=True),
            ],
            "sweeps": [],
            "fvgs": [],
            "order_blocks": [],
            "liquidity_levels": [],
        },
    }


def _default_active_range() -> dict[str, Any]:
    return {
        "selected_range": {
            "status": "RESOLVED_ACTIVE_RANGE",
            "timeframe": "4h",
            "direction": "bullish",
            "range_high": 62180.0,
            "range_low": 57758.6,
            "equilibrium": 59969.3,
            "price_location": "premium",
            "range_id": "BTCUSDT:4h:active_range:test",
            "width_atr": 4.2868,
            "max_width_atr": 22.0,
            "protected_high_pivot_id": "BTCUSDT:4h:swing_high:test",
            "protected_low_pivot_id": "BTCUSDT:4h:swing_low:test",
            "authority_notes": ["Active range from protected swing pair."],
        },
    }


def _evidence_pack_with_graph(*, candidates_override: dict | None = None, ar_override: dict | None = None) -> dict:
    candidates = candidates_override or _default_detector_candidates()
    ar = ar_override or _default_active_range()
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT",
        detector_candidates=candidates,
        active_range_authority=ar,
        decision_time="2026-07-03T12:00:00Z",
    )
    return {"formal_structure_graph": graph, "detector_candidates": candidates, "active_range_authority": ar}


def _decision(*, direction: str = "mixed", official_state: str = "THESIS_ONLY", final_bias: str = "mixed",
               thesis: str = "", evidence: list[str] | None = None, labels: list[dict] | None = None) -> dict:
    if not thesis:
        thesis = "THESIS_ONLY. No trade."
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": official_state,
        "setup_grade": official_state if official_state != "TRADE_PLAN_READY" else "A",
        "direction": direction,
        "setup_model": "test_graph_model",
        "bias_summary": {"daily": "bearish", "4h": "bullish", "1h": "bullish", "final_bias": final_bias, "evidence": evidence or [thesis]},
        "active_range": {"timeframe": "4h", "high": 62180.0, "low": 57758.6, "equilibrium": 59969.3,
                         "price_location": "premium", "source": "protected_swing_pair", "evidence": ["Active range from swing structure."]},
        "liquidity_story": {"obvious_liquidity": [], "swept_liquidity": [], "unswept_liquidity": [], "narrative": thesis},
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": thesis},
        "active_poi": {"poi_id": None, "timeframe": None, "kind": None, "direction": "unknown", "price_low": None, "price_high": None,
                       "freshness": None, "evidence_object_ids": [], "summary": "No active POI."},
        "entry_plan": {"entry_ready": False, "entry_timeframe": "15m", "refinement_timeframe": "5m", "entry_price": None,
                       "entry_zone_low": None, "entry_zone_high": None, "signal_type": None, "required_confirmation": [],
                       "evidence_object_ids": [], "summary": "No entry."},
        "stop_loss_plan": {"stop_price": None, "structural_invalidation_price": None, "source": None, "buffer_notes": None,
                           "evidence_object_ids": [], "summary": "No stop."},
        "target_plan": {"targets": [], "model_completion_liquidity_id": None, "summary": "No targets."},
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "No RR."},
        "invalidation": {"invalidation_price": None, "condition": "No invalidation.", "source": None, "evidence_object_ids": []},
        "annotation_plan": {"chart_template": "context_chart", "show_trade_box": False,
                            "labels": labels or [{"text": thesis, "kind": "context", "timeframe": "4h"}],
                            "levels": [], "reasoning_order": REASONING_ORDER},
        "self_review": {"active_range_check": "passed", "poi_check": "not_applicable", "annotation_check": "passed",
                        "refusal_check": "passed", "corrections_made": [], "remaining_uncertainties": []},
        "final_thesis": thesis,
    }


# ── Core Graph Tests ────────────────────────────────────────────────────


def test_graph_detects_parent_child_conflict() -> None:
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT",
        detector_candidates=_default_detector_candidates(),
        active_range_authority=_default_active_range(),
    )
    assert graph["parent_child_context"]["status"] == "PARENT_CHILD_CONFLICT"
    assert graph["parent_child_context"]["parent_timeframe"] == "1d"
    assert graph["parent_child_context"]["parent_bias"] == "bearish"
    assert graph["parent_child_context"]["child_timeframe"] == "4h"
    assert graph["parent_child_context"]["child_bias"] == "bullish"
    assert "pullback/recovery" in graph["parent_child_context"]["thesis_sentence"]


def test_graph_requires_mixed_bias_when_conflict() -> None:
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT",
        detector_candidates=_default_detector_candidates(),
        active_range_authority=_default_active_range(),
    )
    assert graph_requires_mixed_bias(graph) is True
    assert graph_requires_thesis_only(graph) is True


def test_graph_produces_thesis_sentence() -> None:
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT",
        detector_candidates=_default_detector_candidates(),
        active_range_authority=_default_active_range(),
    )
    sentence = graph_thesis_sentence(graph)
    assert "1d" in sentence
    assert "bearish" in sentence
    assert "4h" in sentence
    assert "bullish" in sentence


def test_graph_with_no_conflict_is_aligned() -> None:
    aligned = {
        "1d": {"structure_breaks": [_break("1d_bull_bos", "bullish", "2026-07-01T00:00:00Z", "external", 60000.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "4h": {"structure_breaks": [_break("4h_bull_bos", "bullish", "2026-07-02T04:00:00Z", "external", 61000.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "1h": {"structure_breaks": [_break("1h_bull_bos", "bullish", "2026-07-03T00:00:00Z", "external", 61500.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "15m": {"structure_breaks": [_break("15m_bull_bos", "bullish", "2026-07-03T10:00:00Z", "external", 61800.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=aligned, active_range_authority=_default_active_range())
    assert graph["parent_child_context"]["status"] == "ALIGNED"
    assert graph_requires_mixed_bias(graph) is False


def test_graph_catches_wick_probes() -> None:
    candidates = {
        "1d": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "4h": {"structure_breaks": [
            _break("4h_wick_probe", "bullish", "2026-07-03T04:00:00Z", "external", 62000.0, is_unconfirmed_probe=True),
        ], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "1h": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "15m": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=candidates, active_range_authority=_default_active_range())
    assert graph["timeframes"]["4h"]["has_wick_probes"] is True
    assert graph["timeframes"]["4h"]["wick_probe_count"] == 1
    # Wick probes existing is normal — they should NOT cause invariant violations
    codes = graph_invariant_violation_codes(graph)
    assert "wick_probes_are_not_breaks" not in codes


def test_graph_rejects_ohlc_summary_range() -> None:
    ar = {"selected_range": {"status": "UNRESOLVED", "source": "ohlcv_summary_high_low"}}
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=ar)
    codes = graph_invariant_violation_codes(graph)
    assert "active_range_from_swing_structure" in codes


def test_graph_timeframes_have_correct_structure() -> None:
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=_default_active_range())
    assert graph["timeframes"]["1d"]["external_bias"] == "bearish"
    assert graph["timeframes"]["4h"]["external_bias"] == "bullish"
    assert graph["timeframes"]["1h"]["external_bias"] == "bullish"
    assert graph["timeframes"]["15m"]["external_bias"] == "bullish"
    assert graph["timeframes"]["15m"]["internal_state"] == "bearish_internal_pullback"


# ── Validator Integration Tests ─────────────────────────────────────────


def test_validator_accepts_thesis_only_when_graph_has_conflict() -> None:
    pack = _evidence_pack_with_graph()
    decision = parse_ai_smc_decision(_decision(
        direction="mixed", official_state="THESIS_ONLY", final_bias="mixed",
        thesis="1d remains bearish parent while 4h is bullish child recovery; treat the child move as pullback/recovery inside parent context.",
    ))
    result = validate_ai_smc_decision(decision, pack)
    assert result.status == "VALIDATED"


def test_validator_rejects_clean_bullish_when_graph_has_conflict() -> None:
    pack = _evidence_pack_with_graph()
    decision = parse_ai_smc_decision(_decision(direction="bullish", official_state="WATCH_ONLY", final_bias="bullish",
                                                thesis="BTC is bullish on 4h and 1h."))
    result = validate_ai_smc_decision(decision, pack)
    codes = {i.code for i in result.issues}
    assert "formal_graph_requires_mixed_bias" in codes


def test_validator_rejects_trade_plan_ready_when_graph_has_conflict() -> None:
    pack = _evidence_pack_with_graph()
    p = _decision(direction="bearish", official_state="TRADE_PLAN_READY", final_bias="bearish",
                  thesis="Short BTC from 62180.")
    p["annotation_plan"]["chart_template"] = "trade_plan_chart"
    p["setup_grade"] = "A"
    decision = parse_ai_smc_decision(p)
    result = validate_ai_smc_decision(decision, pack)
    codes = {i.code for i in result.issues}
    assert "formal_graph_trade_promotion_blocked" in codes


def test_validator_accepts_aligned_graph() -> None:
    aligned_cands = {
        "1d": {"structure_breaks": [_break("1d_bull_bos", "bullish", "2026-07-01T00:00:00Z", "external", 60000.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "4h": {"structure_breaks": [_break("4h_bull_bos", "bullish", "2026-07-02T04:00:00Z", "external", 61000.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "1h": {"structure_breaks": [_break("1h_bull_bos", "bullish", "2026-07-03T00:00:00Z", "external", 61500.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "15m": {"structure_breaks": [_break("15m_bull_bos", "bullish", "2026-07-03T10:00:00Z", "external", 61800.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    pack = _evidence_pack_with_graph(candidates_override=aligned_cands)
    decision = parse_ai_smc_decision(_decision(direction="bullish", official_state="WATCH_ONLY", final_bias="bullish",
                                                thesis="BTC bullish across all timeframes."))
    result = validate_ai_smc_decision(decision, pack)
    assert result.status == "VALIDATED"
    assert not any("formal_graph" in i.code for i in result.issues)


def test_graph_with_12h_parent() -> None:
    candidates = {
        "12h": {"structure_breaks": [_break("12h_bearish_bos", "bearish", "2026-07-02T00:00:00Z", "external", 62272.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "4h": {"structure_breaks": [_break("4h_bull_choch", "bullish", "2026-07-02T04:00:00Z", "external", 60758.0, is_choch=True)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "1h": {"structure_breaks": [_break("1h_bull_bos", "bullish", "2026-07-02T12:00:00Z", "external", 61322.0)], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "15m": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=candidates, active_range_authority=_default_active_range())
    assert graph["parent_child_context"]["status"] == "PARENT_CHILD_CONFLICT"
    assert graph["parent_child_context"]["parent_timeframe"] == "12h"
    assert graph["parent_child_context"]["parent_bias"] == "bearish"
    assert graph["parent_child_context"]["child_timeframe"] == "4h"
    assert graph["parent_child_context"]["child_bias"] == "bullish"


def test_graph_internal_state_continuation() -> None:
    candidates = {
        "1d": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "4h": {"structure_breaks": [
            _break("4h_bear_cont", "bearish", "2026-07-02T00:00:00Z", "external", 62000.0),
        ], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "1h": {"structure_breaks": [
            _break("1h_ext_bear", "bearish", "2026-07-03T00:00:00Z", "external", 61000.0),
            _break("1h_int_bear", "bearish", "2026-07-03T04:00:00Z", "internal", 60800.0),
        ], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
        "15m": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=candidates, active_range_authority=_default_active_range())
    assert graph["timeframes"]["1h"]["internal_state"] == "bearish_internal_continuation"


def test_graph_authority_contract() -> None:
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=_default_active_range())
    contract = graph["authority_contract"]
    assert contract["graph_is_authoritative"] is True
    assert contract["overrides_blocked"] is True
    assert contract["signal_allowed"] is False  # graph is observe-only
    assert contract["invariant_passed"] is True
    assert contract["trade_promotion_blocked"] is True  # blocked by parent-child conflict
    assert contract["execution"] == "disabled"
    assert contract["capital_risk"] == 0
    assert contract["trade_promotion_blocked"] is True


def test_graph_serializes_for_prompt() -> None:
    from smc_desk.perception.formal_structure_graph import graph_to_dict_string
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=_default_active_range())
    s = graph_to_dict_string(graph)
    assert isinstance(s, str)
    parsed = json.loads(s)
    assert parsed["invariant_status"] == "PASS"
    assert parsed["parent_child_context"]["status"] == "PARENT_CHILD_CONFLICT"
    assert "1d" in parsed["parent_child_context"]["thesis_sentence"]


# ── Additional Plan-Required Tests ──────────────────────────────────────


def test_graph_child_body_close_beyond_parent_is_legitimate_flip() -> None:
    """Child body-closes beyond parent protected level → parent flip is legitimate, not a violation."""
    candidates = {
        "1d": {
            "structure_breaks": [
                _break("1d_bear_choch", "bearish", "2026-06-01T00:00:00Z", "external", 60000.0, is_choch=True,
                       broke_protected_swing=True),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "4h": {
            "structure_breaks": [
                _break("4h_bull_choch", "bullish", "2026-07-03T04:00:00Z", "external", 61000.0, is_choch=True,
                       broke_protected_swing=True, body_close_penetration=250.0),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "1h": {
            "structure_breaks": [
                _break("1h_bull_bos", "bullish", "2026-07-03T12:00:00Z", "external", 61500.0),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "15m": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    ar = _default_active_range()
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=candidates, active_range_authority=ar)
    pc = graph["parent_child_context"]
    assert pc["status"] == "PARENT_BREAK_CONFIRMED"
    assert pc["has_conflict"] is False
    assert pc["is_child_body_closed_beyond_parent_protected"] is True
    assert graph_requires_thesis_only(graph) is False
    assert graph_requires_mixed_bias(graph) is False
    inv = graph["invariants"]
    assert inv["status"] == "PASS"
    assert "child_body_close_required_for_parent_break" not in inv["violations"]
    assert "internal_child_cannot_flip_parent" not in inv["violations"]


def test_graph_stale_child_break_cannot_influence_context() -> None:
    """Stale child break older than parent external break does not create a fresh conflict."""
    candidates = {
        "1d": {
            "structure_breaks": [
                _break("1d_bull_bos", "bullish", "2026-07-03T00:00:00Z", "external", 62000.0),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "4h": {
            "structure_breaks": [
                _break("4h_bear_stale", "bearish", "2026-06-01T00:00:00Z", "external", 58000.0, is_choch=True),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "1h": {
            "structure_breaks": [
                _break("1h_bull_bos", "bullish", "2026-07-03T12:00:00Z", "external", 61500.0),
            ],
            "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": [],
        },
        "15m": {"structure_breaks": [], "sweeps": [], "fvgs": [], "order_blocks": [], "liquidity_levels": []},
    }
    graph = build_mtf_structure_graph(symbol="BTCUSDT", detector_candidates=candidates, active_range_authority=_default_active_range())
    pc = graph["parent_child_context"]
    assert pc["status"] == "ALIGNED"
    assert pc["aligned_bias"] == "bullish"
    assert pc["has_conflict"] is False
    assert pc["stale_child_breaks"][0]["child_timeframe"] == "4h"
    assert pc["stale_child_breaks"][0]["child_break_id"] == "4h_bear_stale"


def test_structure_map_renderer_no_trade_box() -> None:
    """Renderer produces a sparse structure map PNG with no trade box."""
    import tempfile
    from pathlib import Path
    import pandas as pd
    from smc_desk.rendering.structure_map_renderer import render_structure_map

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-07-01", periods=50, freq="15min", tz="UTC"),
        "open": [60000.0 + i * 10 for i in range(50)],
        "high": [60100.0 + i * 10 for i in range(50)],
        "low": [59900.0 + i * 10 for i in range(50)],
        "close": [60050.0 + i * 10 for i in range(50)],
        "volume": [1000.0] * 50,
    })
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=_default_active_range()
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "structure_map.png"
        render_structure_map({"15m": df}, graph, out, symbol="BTCUSDT")
        assert out.exists()
        assert out.stat().st_size > 1000


def test_critic_prompt_includes_formal_graph() -> None:
    """Critic prompt (graph challenger) must include the formal_structure_graph."""
    from smc_desk.brain.prompt_system.critic_prompt import build_critic_prompt

    pack = _evidence_pack_with_graph()
    prompt_str = build_critic_prompt({"official_state": "THESIS_ONLY"}, pack)
    prompt = json.loads(prompt_str)
    assert "formal_structure_graph" in prompt
    graph_section = json.loads(prompt["formal_structure_graph"])
    assert graph_section["schema"] == "formal_mtf_structure_graph_v1"
    assert "PARENT_CHILD_CONFLICT" in prompt["formal_structure_graph"]
    instructions_text = " ".join(prompt["instructions"])
    assert "ONLY downgrade" in instructions_text
    assert "NEVER promote" in instructions_text


def test_invariant_detail_uses_correct_timeframe_names() -> None:
    """Invariant detail strings should show actual timeframe names, not None."""
    graph = build_mtf_structure_graph(
        symbol="BTCUSDT", detector_candidates=_default_detector_candidates(), active_range_authority=_default_active_range()
    )
    checks = graph["invariants"]["checks"]
    for check in checks:
        if check["code"] == "internal_child_cannot_flip_parent":
            assert "None" not in check["detail"]
            assert "1d" in check["detail"]
            assert "4h" in check["detail"]
            return
    assert False, "internal_child_cannot_flip_parent check not found"
