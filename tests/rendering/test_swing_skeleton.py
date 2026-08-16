"""The structure skeleton must read as structure, not as a prominence list.

Two pieces of this repository were built and never called: significance ranking
and the HH/HL/LH/LL vocabulary. Joining them exposed a failure that only shows
up on real data -- selecting the strongest swings regardless of side produced
six lows in a row on live BTCUSDT 4h, every label reading "LL", describing
nothing. These tests pin the alternation that makes the sequence legible.
"""
from __future__ import annotations

from dataclasses import dataclass

from smc_desk.perception.significance import SignificanceScore
from smc_desk.rendering.swing_skeleton import build_swing_skeleton, select_skeleton_swings

HIGH = "bearish"  # a swing high tops a bearish turn
LOW = "bullish"   # a swing low bottoms a bullish one


@dataclass
class FakeAnchor:
    object_id: str
    direction: str
    exact_price: float
    end_index: int
    start_index: int = 0
    price_low: float | None = None
    price_high: float | None = None


def score(object_id: str, atr_multiple: float, grade: str = "major") -> SignificanceScore:
    return SignificanceScore(
        object_id=object_id, grade=grade, atr_multiple=atr_multiple, range_fraction=0.3
    )


def cohort(spec):
    """spec: [(id, side, price, index, prominence)] -> (anchors, scores_by_id)"""
    anchors = [FakeAnchor(i, side, price, index) for i, side, price, index, _ in spec]
    scores = {i: score(i, prom) for i, _, _, _, prom in spec}
    return anchors, scores


# -- alternation --------------------------------------------------------------


def test_sides_alternate_even_when_one_side_dominates_prominence() -> None:
    """The live BTCUSDT failure: six strongest swings all lows, every label LL."""
    anchors, scores = cohort([
        ("low1", LOW, 100.0, 1, 9.0), ("low2", LOW, 99.0, 3, 8.9),
        ("low3", LOW, 98.0, 5, 8.8), ("low4", LOW, 97.0, 7, 8.7),
        ("high1", HIGH, 110.0, 2, 2.0), ("high2", HIGH, 109.0, 4, 1.9),
    ])
    selected = select_skeleton_swings(anchors, scores, limit=4)
    sides = [a.direction for a in selected]
    assert sides.count(HIGH) == 2 and sides.count(LOW) == 2, sides


def test_a_one_sided_market_still_gets_a_skeleton() -> None:
    """Alternation is a preference, not a requirement that empties the chart."""
    anchors, scores = cohort([
        ("l1", LOW, 100.0, 1, 5.0), ("l2", LOW, 99.0, 2, 4.0), ("l3", LOW, 98.0, 3, 3.0),
    ])
    assert len(select_skeleton_swings(anchors, scores, limit=4)) == 3


def test_prominence_still_picks_which_high_and_which_low() -> None:
    anchors, scores = cohort([
        ("weak_high", HIGH, 110.0, 1, 1.0), ("strong_high", HIGH, 112.0, 2, 9.0),
        ("weak_low", LOW, 100.0, 3, 1.1), ("strong_low", LOW, 98.0, 4, 8.0),
    ])
    chosen = {a.object_id for a in select_skeleton_swings(anchors, scores, limit=2)}
    assert chosen == {"strong_high", "strong_low"}


def test_output_is_in_chart_order_not_rank_order() -> None:
    anchors, scores = cohort([
        ("late_high", HIGH, 110.0, 90, 9.0), ("early_low", LOW, 100.0, 5, 8.0),
    ])
    assert [a.object_id for a in select_skeleton_swings(anchors, scores, limit=2)] == [
        "early_low", "late_high"
    ]


# -- labelling ----------------------------------------------------------------


def test_labels_compare_against_the_previous_drawn_swing_on_the_same_side() -> None:
    anchors, scores = cohort([
        ("h1", HIGH, 110.0, 1, 9.0), ("l1", LOW, 100.0, 2, 9.0),
        ("h2", HIGH, 108.0, 3, 8.0), ("l2", LOW, 98.0, 4, 8.0),
    ])
    labels = [o["label"] for o in build_swing_skeleton(anchors, scores, timeframe="4h", limit=4)]
    # First of each side has no predecessor: named, but no relationship claimed.
    assert labels == ["H", "L", "LH", "LL"]


def test_a_rising_sequence_reads_as_higher_highs_and_higher_lows() -> None:
    anchors, scores = cohort([
        ("h1", HIGH, 105.0, 1, 9.0), ("l1", LOW, 100.0, 2, 9.0),
        ("h2", HIGH, 112.0, 3, 8.0), ("l2", LOW, 104.0, 4, 8.0),
    ])
    labels = [o["label"] for o in build_swing_skeleton(anchors, scores, timeframe="4h", limit=4)]
    assert labels == ["H", "L", "HH", "HL"]


def test_the_first_swing_on_each_side_is_never_given_an_unfounded_label() -> None:
    """Named as a high, but not claimed to be higher or lower than anything."""
    anchors, scores = cohort([("h1", HIGH, 110.0, 1, 9.0)])
    label = build_swing_skeleton(anchors, scores, timeframe="1d", limit=4)[0]["label"]
    assert label == "H"
    assert label not in {"HH", "LH"}


def test_no_marker_is_ever_emitted_without_a_label() -> None:
    """An empty label makes the renderer fall back to the object kind and print
    "SWING_HIGH" across the chart, louder than the real structure labels."""
    spec = [(f"o{i}", HIGH if i % 2 else LOW, 100.0 + i, i, 5.0) for i in range(8)]
    anchors, scores = cohort(spec)
    for marker in build_swing_skeleton(anchors, scores, timeframe="4h", limit=6):
        assert marker["label"], marker


# -- refusal and hygiene ------------------------------------------------------


def test_ungraded_swings_are_dropped_not_assumed_significant() -> None:
    anchors, scores = cohort([("h1", HIGH, 110.0, 1, 9.0)])
    anchors.append(FakeAnchor("unscored", LOW, 100.0, 2))
    selected = select_skeleton_swings(anchors, scores, limit=4)
    assert [a.object_id for a in selected] == ["h1"]


def test_below_minimum_grade_is_excluded() -> None:
    anchors = [FakeAnchor("noisy", HIGH, 110.0, 1)]
    scores = {"noisy": score("noisy", 0.1, grade="noise")}
    assert select_skeleton_swings(anchors, scores, limit=4) == []


def test_limit_is_respected() -> None:
    spec = [(f"o{i}", HIGH if i % 2 else LOW, 100.0 + i, i, 5.0) for i in range(20)]
    anchors, scores = cohort(spec)
    assert len(select_skeleton_swings(anchors, scores, limit=6)) == 6


def test_empty_input_yields_no_marks() -> None:
    assert build_swing_skeleton([], {}, timeframe="4h") == []


def test_markers_carry_their_grade_and_evidence() -> None:
    anchors, scores = cohort([("h1", HIGH, 110.0, 1, 9.0)])
    marker = build_swing_skeleton(anchors, scores, timeframe="4h")[0]
    assert marker["object_type"] == "swing_marker"
    assert marker["kind"] == "swing_high"
    assert marker["significance_grade"] == "major"
    assert marker["evidence_object_ids"] == ["h1"]
    assert marker["price"] == 110.0


def test_selection_is_deterministic() -> None:
    spec = [(f"o{i}", HIGH if i % 2 else LOW, 100.0 + i, i, 5.0) for i in range(12)]
    anchors, scores = cohort(spec)
    first = [a.object_id for a in select_skeleton_swings(anchors, scores, limit=6)]
    second = [a.object_id for a in select_skeleton_swings(list(reversed(anchors)), scores, limit=6)]
    assert first == second


def test_the_same_pivot_seen_at_three_scales_is_drawn_once() -> None:
    """Live XRPUSDT 4h emitted one low three times, labelled L, LL and LL.

    The detector runs at local, internal and external scales, so a single
    extreme appears repeatedly at the same price. Without deduplication the
    second and third compare the swing against itself and conclude it made a
    lower low than itself, which is not a statement about the market.
    """
    anchors, scores = cohort([
        ("local",    LOW, 0.9993, 110, 5.0),
        ("internal", LOW, 0.9993, 112, 6.0),
        ("external", LOW, 0.9993, 114, 7.0),
        ("a_high",   HIGH, 1.0908, 13, 9.0),
    ])
    markers = build_swing_skeleton(anchors, scores, timeframe="4h", limit=6)
    lows = [m for m in markers if m["kind"] == "swing_low"]
    assert len(lows) == 1, [m["label"] for m in markers]
    assert lows[0]["label"] == "L"
    assert "LL" not in [m["label"] for m in markers]


def test_genuinely_different_lows_are_both_kept() -> None:
    """Deduplication must not collapse a real lower low into its predecessor."""
    anchors, scores = cohort([
        ("first_low",  LOW, 1.0500, 10, 9.0),
        ("second_low", LOW, 0.9900, 40, 8.0),
        ("a_high",     HIGH, 1.1000, 25, 9.0),
    ])
    markers = build_swing_skeleton(anchors, scores, timeframe="4h", limit=6)
    lows = [m["label"] for m in markers if m["kind"] == "swing_low"]
    assert lows == ["L", "LL"]
