"""Tests for the anchor-preserving retriever and retrieval tools (step 3).

Pins the programme §4.6 anchor contract:

  * The retriever ALWAYS preserves the eight anchor kinds (active external
    high/low, protected point, range endpoints, BOS origins, active HTF
    POIs, unswept external liquidity, blind-reader refs, critic challenges),
    regardless of the fill budget.
  * Missing anchors are reported explicitly, not silently dropped.
  * Fill ranks by causal > timeframe importance > active lifecycle > recency.
  * The four A/B designs (full, flat, anchor, anchor_tools) share a uniform
    stats shape and the anchor design wins on anchor-preservation at fixed
    budget.
  * Retrieval tools answer real calls and refuse unknown tools cleanly.
"""
from __future__ import annotations

import pytest

from smc_desk.brain.structure_lab.ab_designs import ALL_DESIGNS, build_candidate_payload
from smc_desk.brain.structure_lab.context_retriever import (
    ANCHOR_KINDS,
    retrieve_for_case,
    to_compact_payload,
)
from smc_desk.brain.structure_lab.tools import (
    TOOL_DEFINITIONS,
    RetrievalTools,
)


def _case():
    """Case fixture shaped like the REAL formal_mtf_structure_graph_v1 output.

    The graph emits protected_high/low per timeframe node, an active_range
    with protected_*_swing_id fields, latest_external_break events, and (on
    real runs) integer COUNTS for liquidity_levels — the 4h node below pins
    that the adapter tolerates counts without crashing.
    """
    return {
        "candidate_objects": {
            "15m": {"swings": [
                {"object_id": f"s{i}", "confirmed_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                 "timeframe": "15m", "pivot_price": 100 + i, "lifecycle": "CANDIDATE"}
                for i in range(100)
            ]},
            "1h": {"swings": [
                {"object_id": f"h{i}", "confirmed_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                 "timeframe": "1h", "pivot_price": 50 + i, "lifecycle": "CANDIDATE"}
                for i in range(20)
            ]},
        },
        "formal_structure_graph": {
            "schema": "formal_mtf_structure_graph_v1",
            "active_range": {
                "status": "RESOLVED",
                "range_id": "range_15m",
                "protected_high_swing_id": "s10",
                "protected_low_swing_id": "s5",
            },
            "timeframes": {
                "15m": {
                    "latest_external_break": {
                        "object_id": "br1", "direction": "bullish",
                        "origin_object_id": "s3", "confirmed_at": "2026-01-20T00:00:00Z",
                    },
                    "liquidity_levels": [
                        {"liquidity_id": "liq_eq_lows", "activity_status": "active"},
                        {"liquidity_id": "liq_swept", "activity_status": "consumed"},
                    ],
                },
                "1h": {
                    "latest_external_break": {
                        "object_id": "br2", "direction": "bearish",
                        "origin_object_id": "h12", "confirmed_at": "2026-01-21T00:00:00Z",
                    },
                },
                "4h": {
                    "order_blocks": [{"object_id": "poi_4h", "timeframe": "4h"}],
                    "liquidity_levels": 3,   # real graph emits a count here
                },
            },
        },
        "blind_reader_reference_ids": ["h7", "ghost_ref"],
        "critic_challenges": ["h3"],
    }


def test_eight_anchor_kinds_are_defined():
    assert set(ANCHOR_KINDS) == {
        "active_external_high", "active_external_low", "protected_point",
        "range_endpoint", "break_origin", "htf_active_poi",
        "unswept_external_liquidity", "blind_reader_reference", "critic_challenge",
    }


def test_anchors_always_preserved_even_with_zero_budget():
    """The anchor set ALWAYS fits (programme §4.6) regardless of fill budget."""
    case = _case()
    res_full = retrieve_for_case(case, fill_budget=600)
    res_tiny = retrieve_for_case(case, fill_budget=0)
    # Anchor count is identical across budgets -- the anchor set is not
    # bounded by fill_budget.
    assert len(res_tiny.anchor_records) == len(res_full.anchor_records)
    # Zero budget => empty fill; 600 budget => all non-anchor candidates fit.
    assert len(res_tiny.fill) == 0
    assert len(res_full.fill) >= 100


def test_missing_anchors_are_reported_not_dropped():
    """Anchors that resolve nowhere are flagged; graph anchors carry their records.

    Graph-derived anchors (range, breaks, HTF POIs) resolve from their own
    graph records even when absent from the candidate pool — the audit's
    "range preserved only as a missing placeholder" failure. Only references
    that resolve nowhere (a blind-reader id that exists in no evidence) are
    reported missing.
    """
    case = _case()
    res = retrieve_for_case(case, fill_budget=0)
    assert "ghost_ref" in res.missing_anchor_ids
    assert "range_15m" not in res.missing_anchor_ids
    assert "h7" not in res.missing_anchor_ids
    avail = {r["object_id"]: r.get("_available") for r in res.anchor_records if r.get("object_id")}
    assert avail["ghost_ref"] is False
    assert avail["range_15m"] is True    # resolved from its graph record
    assert avail["poi_4h"] is True       # resolved from its graph record
    assert avail["s5"] is True           # resolved from the candidate pool
    assert avail["h7"] is True
    # Consumed liquidity must NOT be anchored; active liquidity must be.
    anchored = {a.candidate_id for a in res.anchors}
    assert "liq_eq_lows" in anchored
    assert "liq_swept" not in anchored


def test_all_four_ab_designs_share_uniform_stats():
    case = _case()
    seen: dict[str, dict] = {}
    for d in ALL_DESIGNS:
        p = build_candidate_payload(case, design=d)
        seen[d] = p["stats"]
        for key in (
            "design", "fill_count", "estimated_bytes",
            "anchors_required", "anchors_preserved",
            "missing_anchor_ids", "dropped_from_fill_count",
        ):
            assert key in p["stats"], f"{d} missing {key} in stats"


def test_anchor_design_preserves_anchors_flat_design_does_not():
    case = _case()
    flat = build_candidate_payload(case, design="flat")
    anchor = build_candidate_payload(case, design="anchor_tools", anchor_fill_budget=5)
    assert flat["stats"]["anchors_required"] == 0     # flat has no anchor concept
    # 10 AnchorHits derive from the case: range high/low + range endpoint,
    # two break origins, one HTF POI, one active liquidity, blind h7 +
    # ghost_ref, critic h3. Only ghost_ref resolves nowhere.
    assert anchor["stats"]["anchors_required"] == 10
    assert anchor["stats"]["anchors_preserved"] == 9
    assert anchor["stats"]["missing_anchor_ids"] == ["ghost_ref"]
    # Critically: even at fill_budget=0 the available anchor set still fits.
    zero = build_candidate_payload(case, design="anchor", anchor_fill_budget=0)
    assert zero["stats"]["anchors_preserved"] == 9


def test_anchor_tools_attaches_tool_definitions():
    case = _case()
    p = build_candidate_payload(case, design="anchor_tools")
    assert p["candidate_objects"].get("tools_attached") is True
    tools = p["candidate_objects"]["tools"]
    names = {t["name"] for t in tools}
    assert {"get_candidate", "search_candidates", "get_parent_chain", "get_break_origin"} <= names


def test_context_is_hash_pinned_for_drift_detection():
    case = _case()
    a = retrieve_for_case(case, fill_budget=10)
    b = retrieve_for_case(case, fill_budget=10)
    assert a.sha256 == b.sha256


def test_retrieval_tools_answer_real_calls():
    case = _case()
    pool = [c for tf in case["candidate_objects"].values() for bs in tf.values() for c in bs]
    t = RetrievalTools(pool, case["formal_structure_graph"])

    assert t.handle({"tool": "get_candidate", "arguments": {"candidate_id": "s5"}})["result"]["found"] is True
    assert t.handle({"tool": "get_candidate", "arguments": {"candidate_id": "ZZZ"}})["result"]["found"] is False

    res = t.handle({"tool": "search_candidates", "arguments": {"timeframe": "1h"}})["result"]
    assert len(res) == 20

    res = t.handle({"tool": "get_break_origin", "arguments": {"event_id": "br1"}})["result"]
    assert res["found"] is True and res["origin"]["found"] is True
    # unknown break
    res = t.handle({"tool": "get_break_origin", "arguments": {"event_id": "ghost"}})["result"]
    assert res["found"] is False


def test_unknown_tool_returns_error_not_crash():
    case = _case()
    pool = [c for tf in case["candidate_objects"].values() for bs in tf.values() for c in bs]
    t = RetrievalTools(pool, case["formal_structure_graph"])
    out = t.handle({"tool": "nope", "arguments": {}})
    assert out["ok"] is False


def test_doctrine_anchors_preservation_principle_present():
    from smc_desk.structure.doctrine import doctrine
    d = doctrine()
    ids = {p.get("id") for p in d.design_principles}
    assert "anchor_preservation" in ids


def test_compact_payload_shape_includes_required_fields():
    case = _case()
    res = retrieve_for_case(case, fill_budget=2)
    payload = to_compact_payload(res)
    for key in ("schema", "anchors", "candidates", "fill", "dropped_from_fill",
                "missing_anchor_ids", "budget", "sha256"):
        assert key in payload, f"missing {key}"
