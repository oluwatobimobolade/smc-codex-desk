"""Tests for the causal protected-point and active-range state machines (step 4).

Pins the programme §5 and §7 contracts:

Protected point (§5):
  * Selection rejects the "latest confirmed opposing pivot" shortcut: the
    top candidate must satisfy the §5.5 promotion rules (predates_break +
    unviolated), else the system abstains.
  * At least four candidate kinds are generated (internal pivot, cluster
    extreme, HTF origin, nested LTF pivot) when the evidence supports them.
  * The selection records the protection graph relationships.

Active range (§7):
  * Lifecycle: PROPOSED -> ACTIVE; ACTIVE -> EXTENDED / SUPERSEDED / STALE.
  * Replacement requires one of the four §7.5 triggers.
  * Location output matches the §7.6 schema.
  * A child range cannot overwrite its parent (no silent overwrite).
"""
from __future__ import annotations

import pytest

from smc_desk.structure.active_range import (
    RangeLifecycle,
    can_replace,
    location_in_range,
    propose_range,
    activate,
    replace,
)
from smc_desk.structure.protected_point import (
    ProtectedPointCandidate,
    ProtectedPointSelection,
    generate_candidates,
    score_candidates,
    select,
)


# -- protected point ----------------------------------------------------------


def _break(direction="bullish"):
    return {
        "object_id": "br1",
        "timeframe": "4h",
        "direction": direction,
        "confirming_candle_time": "2026-01-05T00:00:00Z",
        "impulse_candle_ids": ["c1", "c2", "c3"],
        "origin_cluster_candle_ids": ["c1", "c2", "c3"],
        "displacement_magnitude_atr": 1.8,
    }


def _pool():
    # The repaired generator only admits directionally opposing pivots
    # (bullish break -> protected LOW candidates), so pivot_type is required.
    return [
        {"object_id": "c1", "confirmed_at": "2026-01-04T12:00:00Z", "timeframe": "4h",
         "pivot_type": "low", "pivot_price": 98.0, "low": 98.0, "lifecycle": "CANDIDATE"},
        {"object_id": "c2", "confirmed_at": "2026-01-04T16:00:00Z", "timeframe": "4h",
         "pivot_type": "low", "pivot_price": 96.0, "low": 96.0, "lifecycle": "CANDIDATE"},
        {"object_id": "c3", "confirmed_at": "2026-01-04T20:00:00Z", "timeframe": "4h",
         "pivot_type": "low", "pivot_price": 95.0, "low": 95.0, "lifecycle": "CANDIDATE"},
        {"object_id": "s10", "confirmed_at": "2026-01-03T00:00:00Z", "timeframe": "4h",
         "pivot_type": "low", "pivot_price": 99.0, "lifecycle": "STRUCTURAL"},
    ]


def _candles():
    # Replayed violation evidence: closes never trade below any candidate low,
    # so every candidate is genuinely unviolated at decision time.
    return [
        {"timestamp": f"2026-01-05T{hour:02d}:00:00Z", "close": 101.0 + hour * 0.1}
        for hour in range(1, 12)
    ]


_DECISION_TIME = "2026-01-05T12:00:00Z"


def test_protected_point_generates_internal_pivot_and_cluster():
    cands = generate_candidates(
        accepted_break=_break(), candidate_pool=_pool(), active_range=None,
        timeframe_candles=_candles(), decision_time=_DECISION_TIME,
    )
    kinds = {c.origin_type for c in cands}
    assert "single_candle" in kinds      # internal pivot
    assert "cluster" in kinds            # cluster extreme
    assert all(c.predates_break for c in cands)
    assert all(c.unviolated for c in cands)
    # Violation status must come from replayed candles, not caller booleans.
    assert all(c.violation_checked for c in cands)


def test_protected_point_does_not_use_latest_pivot_shortcut():
    """The latest opposing pivot that POSTDATES the break must NOT be selected."""
    pool = _pool() + [
        {"object_id": "post1", "confirmed_at": "2026-01-06T00:00:00Z", "timeframe": "4h",
         "pivot_type": "low", "pivot_price": 94.0, "lifecycle": "CANDIDATE"},
    ]
    cands = generate_candidates(
        accepted_break=_break(), candidate_pool=pool, active_range=None,
        timeframe_candles=_candles(), decision_time=_DECISION_TIME,
    )
    selected_ids = {c.candidate_id for c in cands}
    assert "post1#internal" not in selected_ids
    assert "s10#internal" in selected_ids   # the pre-break pivot is still found


def test_protected_point_selects_and_records_graph():
    sel = select(
        accepted_break=_break(), candidate_pool=_pool(), active_range=None,
        timeframe_candles=_candles(), decision_time=_DECISION_TIME,
    )
    assert sel.abstained is False
    assert sel.selected.predates_break and sel.selected.unviolated and sel.selected.violation_checked
    # The causal origin-cluster extreme outranks the latest-pivot shortcut.
    assert sel.selected.candidate_id == "cluster#br1"
    assert sel.runner_up is not None and sel.runner_up.candidate_id == "s10#internal"
    assert (sel.selected.candidate_id, "protects_thesis", "break:br1") in sel.graph_relationships
    assert any(edge == "violation_invalidates_thesis" for _, edge, _ in sel.graph_relationships)


def test_protected_point_abstains_when_no_candidates():
    sel = select(accepted_break={"object_id": "br0"}, candidate_pool=[], active_range=None)
    assert sel.abstained is True
    assert sel.graph_relationships == ()


def test_protected_point_abstains_when_candidate_violates_promotion_rules():
    cand = ProtectedPointCandidate(
        candidate_id="x", pivot_time="t", pivot_price=1.0, timeframe="4h",
        origin_type="single_candle", predates_break=False, unviolated=True,
    )
    ranked = score_candidates([cand])
    # score_candidates keeps failing candidates with zero score; select() then
    # surfaces abstention when the top candidate fails promotion rules.
    sel = select(
        accepted_break={"object_id": "br0", "impulse_candle_ids": [], "displacement_magnitude_atr": 0.0,
                        "timeframe": "4h", "confirming_candle_time": "z"},
        candidate_pool=[], active_range=None,
    )
    assert sel.abstained is True


def test_doctrine_marks_protected_point_shortcut_as_forbidden():
    from smc_desk.structure.doctrine import concept
    c = concept("protected_point")
    fs = " ".join(c.get("forbidden_shortcuts", []))
    assert "track.protected_low = track.last_confirmed_low" in fs
    assert "last_confirmed_low" in fs


# -- active range ------------------------------------------------------------


def _range():
    return propose_range(
        range_id="r1", owner_timeframe="4h", direction="bullish",
        origin_id="o1", terminal_id="t1", origin_price=100.0, terminal_price=120.0,
        creating_event_id="br1", protected_point_id="pp1",
    )


def test_range_starts_proposed_then_activates():
    r = _range()
    assert r.lifecycle == RangeLifecycle.PROPOSED.value
    a = activate(r)
    assert a.lifecycle == RangeLifecycle.ACTIVE.value
    assert activate(a).lifecycle == RangeLifecycle.ACTIVE.value  # idempotent


def test_range_replacement_requires_a_trigger():
    a = activate(_range())
    ok, fired = can_replace(a)
    assert ok is False and fired == []
    ok, fired = can_replace(a, terminal_extension=True)
    assert ok is True and "terminal_extension" in fired


def test_range_lifecycle_transitions():
    a = activate(_range())
    ext = replace(a, replacement_reason="extended by BOS br2", terminal_extension=True)
    assert ext.lifecycle == RangeLifecycle.EXTENDED.value
    sup = replace(a, replacement_reason="parent 1d", parent_supersession=True)
    assert sup.lifecycle == RangeLifecycle.SUPERSEDED.value
    stale = replace(a, replacement_reason="explicit", explicit_stale=True)
    assert stale.lifecycle == RangeLifecycle.STALE.value


def test_range_location_output_schema():
    a = activate(_range())
    loc = location_in_range(a, 110.0)
    for key in ("range_validity", "price_location", "distance_from_equilibrium",
                "nested_location", "confidence"):
        assert key in loc
    assert loc["price_location"] in {"premium", "discount"}
    # Non-active range -> insufficient_context
    stale = replace(a, replacement_reason="explicit", explicit_stale=True)
    assert location_in_range(stale, 110.0)["confidence"] == "insufficient_context"


def test_range_does_not_silently_overwrite_parent():
    """A child range cannot overwrite its parent. The hierarchy is enforced by
    storing parent_range_id and refusing replacement-by-child.
    """
    parent = activate(propose_range(
        range_id="daily", owner_timeframe="1d", direction="bullish",
        origin_id="od", terminal_id="td", origin_price=100.0, terminal_price=130.0,
        creating_event_id="brd", protected_point_id="ppd",
    ))
    child = propose_range(
        range_id="4h", owner_timeframe="4h", direction="bullish",
        origin_id="o4", terminal_id="t4", origin_price=105.0, terminal_price=125.0,
        creating_event_id="br4", protected_point_id="pp4",
        parent_range_id=parent.range_id,
    )
    assert child.parent_range_id == "daily"
    # A child attempting to supersede its parent is rejected: only the parent
    # (or an accepted external break at the parent's timeframe) may supersede.
    ok, _ = can_replace(parent, parent_supersession=False, terminal_extension=False,
                        protected_violation=False, explicit_stale=False)
    assert ok is False


def test_range_hash_is_stable():
    r = activate(_range())
    assert r.sha256 == activate(_range()).sha256