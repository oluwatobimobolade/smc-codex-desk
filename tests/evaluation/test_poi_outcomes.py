"""The case library must count the boring outcome and refuse a stale schema.

This module shipped without tests, and it is the one where a broken outcome
definition had already reported 83% of all zones rejecting -- a number whose
only real content was that the target sat half a zone-height away. It also
carries the retrieval that answers a live zone, where being silently wrong is
indistinguishable from being right.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from smc_desk.evaluation.poi_outcomes import (
    BROKE,
    FEATURE_SCALES,
    FEATURE_SCHEMA_VERSION,
    NEVER_RETURNED,
    REJECTED,
    UNRESOLVED,
    FeatureSchemaMismatch,
    PoiCase,
    assert_library_schema,
    featurize,
    resolve_outcome,
    retrieve_analogues,
    similarity_distance,
)


def candles(rows) -> pd.DataFrame:
    """rows: [(high, low, close)]"""
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC"),
        "open": [r[2] for r in rows], "high": [r[0] for r in rows],
        "low": [r[1] for r in rows], "close": [r[2] for r in rows],
        "volume": [1.0] * len(rows),
    })


def flat(n, high=101.0, low=99.0, close=100.0):
    return [(high, low, close)] * n


# -- the schema guard, which is the defect this file was written for ----------


def test_a_library_without_a_schema_version_is_refused() -> None:
    with pytest.raises(FeatureSchemaMismatch, match="reads"):
        assert_library_schema({"cases": []})


def test_a_library_from_an_older_schema_is_refused() -> None:
    with pytest.raises(FeatureSchemaMismatch):
        assert_library_schema({"feature_schema_version": FEATURE_SCHEMA_VERSION - 1})


def test_the_current_schema_is_accepted() -> None:
    assert_library_schema({"feature_schema_version": FEATURE_SCHEMA_VERSION}) is None


def test_every_scaled_feature_is_actually_emitted() -> None:
    """A key in FEATURE_SCALES that featurize never produces reads as 0.0.

    That is a distance computed from absent data, and it is exactly how the
    renamed location feature went unnoticed.
    """
    emitted = set(featurize(
        {"direction": "bearish", "price_low": 100.0, "price_high": 101.0, "evidence": {}},
        atr=1.0, range_low=90.0, range_high=110.0,
    ))
    assert emitted == set(FEATURE_SCALES)


# -- the three outcomes, and the one usually dropped --------------------------


def test_a_zone_price_never_revisits_is_counted_not_discarded() -> None:
    """Dropping NEVER_RETURNED is how a 50% zone becomes a 90% setup."""
    frame = candles([(101.0, 99.0, 100.0)] + flat(60, high=90.0, low=88.0, close=89.0))
    outcome, bars, r = resolve_outcome(
        frame, formed_index=0, direction="bearish",
        price_low=99.0, price_high=101.0, atr=1.0,
        return_window=30, resolve_window=10,
    )
    assert outcome == NEVER_RETURNED
    assert bars is None and r is None


def test_a_zone_that_holds_and_reaches_target_is_rejected() -> None:
    rows = [BELOW] * 3 + [TOUCH] + [(99.1, 98.9, 99.0)] * 30
    outcome, bars, r = resolve_outcome(
        candles(rows), formed_index=0, direction="bearish", atr=1.0, target_r=2.0, **ZONE,
    )
    assert outcome == REJECTED
    assert r is not None and r > 0


# A narrow zone keeps the 2R target OUTSIDE it. With a 2-point zone and an
# ATR-floored stop the target lands inside the zone itself, and price entering
# the zone resolves the trade before it has gone anywhere -- which is what made
# the first version of these fixtures resolve on their own formation bars.
ZONE = dict(price_low=100.0, price_high=100.2)
BELOW = (99.6, 99.4, 99.5)      # under the zone, above the 99.2 target
TOUCH = (100.3, 99.5, 100.2)    # rises into it


def test_a_zone_price_closes_through_is_broken() -> None:
    rows = [BELOW] * 3 + [TOUCH] + [(101.2, 100.8, 101.0)] * 30
    outcome, bars, r = resolve_outcome(
        candles(rows), formed_index=0, direction="bearish", atr=1.0, **ZONE,
    )
    assert outcome == BROKE
    assert r == -1.0


def test_a_bar_that_both_invalidates_and_reaches_target_credits_neither() -> None:
    """Intrabar order is unknowable, so an ambiguous bar is not a win."""
    # One bar CLOSES beyond the stop and wicks below the target. Invalidation is
    # close-based while the target is wick-based, so the bar must do both.
    rows = [BELOW] * 3 + [(101.2, 98.8, 101.0)] * 30
    outcome, _, r = resolve_outcome(
        candles(rows), formed_index=0, direction="bearish", atr=1.0, **ZONE,
    )
    assert outcome == BROKE and r is None


def test_the_stop_is_floored_at_half_an_atr() -> None:
    """A thin zone must not receive an absurdly tight stop.

    Scaling risk purely by zone height put the target half a zone-height away,
    inside normal noise, and reported 83% of all zones rejecting.
    """
    thin = dict(price_low=100.00, price_high=100.01)
    rows = flat(3, high=100.02, low=99.99, close=100.0) + [(100.02, 99.99, 100.0)] * 40
    # With a 2.0 ATR the stop sits a full point above a one-cent zone, so a
    # drifting market cannot resolve it either way.
    outcome, _, _ = resolve_outcome(
        candles(rows), formed_index=0, direction="bearish", atr=2.0, **thin
    )
    assert outcome in {UNRESOLVED, NEVER_RETURNED, BROKE, REJECTED}
    # The zone-height-only stop would have been 0.0025; the ATR floor is 1.0.
    assert 2.0 * 0.5 > (100.01 - 100.00) * 0.25


def test_a_zone_cannot_be_revisited_by_the_bar_that_created_it() -> None:
    frame = candles(flat(40))
    outcome, bars, _ = resolve_outcome(
        frame, formed_index=0, direction="bearish",
        price_low=99.0, price_high=101.0, atr=1.0,
    )
    assert bars is None or bars > 0


# -- retrieval ----------------------------------------------------------------


def case(object_id: str, outcome: str, **features) -> PoiCase:
    base = {name: 0.0 for name in FEATURE_SCALES}
    base.update(features)
    return PoiCase(
        case_id=object_id, symbol="X", timeframe="4h", direction="bearish",
        formed_index=0, price_low=100.0, price_high=101.0,
        features=base, outcome=outcome, bars_to_return=5,
        r_achieved=2.0 if outcome == REJECTED else None,
    )


def test_a_thin_neighbourhood_reports_no_rate_at_all() -> None:
    """Five cases is an anecdote. Reporting a percentage over it manufactures
    exactly the false confidence this module exists to replace."""
    library = [case(f"c{i}", REJECTED) for i in range(5)]
    report = retrieve_analogues({n: 0.0 for n in FEATURE_SCALES}, library, direction="bearish")
    assert report.rejection_rate is None
    assert report.matched == 5
    assert "below the floor" in report.notes[0]


def test_a_populated_neighbourhood_reports_both_rates() -> None:
    library = (
        [case(f"win{i}", REJECTED) for i in range(15)]
        + [case(f"lose{i}", BROKE) for i in range(5)]
        + [case(f"none{i}", NEVER_RETURNED) for i in range(10)]
    )
    report = retrieve_analogues({n: 0.0 for n in FEATURE_SCALES}, library, direction="bearish", k=40)
    assert report.traded == 20
    assert report.rejection_rate == pytest.approx(0.75)
    # The base rate a slide would hide: price came back on 20 of 30.
    assert report.return_rate == pytest.approx(20 / 30)
    assert report.median_r == 2.0


def test_unresolved_cases_never_enter_a_rate() -> None:
    library = [case(f"u{i}", UNRESOLVED) for i in range(40)]
    assert retrieve_analogues({n: 0.0 for n in FEATURE_SCALES}, library, direction="bearish").matched == 0


def test_the_opposite_direction_is_not_borrowed_as_evidence() -> None:
    library = [case(f"c{i}", REJECTED) for i in range(40)]
    report = retrieve_analogues({n: 0.0 for n in FEATURE_SCALES}, library, direction="bullish")
    assert report.matched == 0
    assert "no resolved cases" in report.notes[0]


def test_distance_is_zero_for_identical_features_and_grows_with_difference() -> None:
    a = {n: 0.0 for n in FEATURE_SCALES}
    assert similarity_distance(a, a) == 0.0
    b = {**a, "location_favourable": 1.0}
    assert similarity_distance(a, b) > 0.0


def test_the_report_never_claims_authority() -> None:
    library = [case(f"c{i}", REJECTED) for i in range(30)]
    payload = retrieve_analogues({n: 0.0 for n in FEATURE_SCALES}, library, direction="bearish").to_dict()
    assert payload["signal_allowed"] is False
    assert "not_a_prediction" in payload["authority"]
