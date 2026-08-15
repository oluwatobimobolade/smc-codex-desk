"""The mechanism rung must be able to say no, and must be able to say yes.

A test harness that never finds an effect is useless, and one that finds effects
in noise is worse than useless. Both directions are pinned here: a random walk
must not reach MECHANISM_SUPPORTED, and a deliberately planted drift must.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from smc_desk.evaluation.matched_baseline import (
    balance_report,
    sample_matched_controls,
)
from smc_desk.evaluation.mechanism_evidence import (
    benjamini_hochberg,
    certify_mechanism,
    forward_returns,
    load_preregistration,
    paired_block_bootstrap,
    realised_range_expansion,
)

ROOT = Path(__file__).resolve().parents[2]


def random_walk(n: int = 4000, seed: int = 7, start: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.4, n)
    close = start + np.cumsum(steps)
    high = close + np.abs(rng.normal(0.0, 0.2, n))
    low = close - np.abs(rng.normal(0.0, 0.2, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close, "high": high, "low": low, "close": close, "volume": 1.0,
    })


# A configuration that can actually reach a verdict. Events must be sparse
# enough relative to the 40-bar horizon that uncontaminated controls exist, and
# numerous enough to clear the preregistered floor of 100. Testing a frequent
# pattern at a long horizon is genuinely hard, and using dense events here would
# make every result UNDERPOWERED -- which would let a "does not certify noise"
# test pass without ever exercising the statistics.
POWERED_BARS = 24_000
POWERED_EVENTS = list(range(400, 23_000, 90))


def _assert_reached_a_verdict(result: dict) -> None:
    assert result["status"] in {"MECHANISM_SUPPORTED", "MECHANISM_NOT_SUPPORTED", "BOUNDARY_SENSITIVE"}, (
        f"expected a real verdict, got {result['status']}: {result.get('reason')}"
    )


# -- the seal -----------------------------------------------------------------


def test_preregistration_is_sealed_and_loads() -> None:
    prereg = load_preregistration()
    assert prereg.document["schema"] == "smc_codex_mechanism_preregistration_v1"
    assert prereg.hypothesis("FVG_CONTINUATION_V1") is not None
    assert prereg.contract["minimum_abs_t_statistic"] == 3.0


def test_tampered_preregistration_fails_closed(tmp_path: Path) -> None:
    source = ROOT / "specs" / "MECHANISM_PREREGISTRATION_V1.yaml"
    copy = tmp_path / "prereg.yaml"
    seal = tmp_path / "prereg.sha256"
    copy.write_text(source.read_text(encoding="utf-8") + "\n# added later\n", encoding="utf-8")
    seal.write_text((ROOT / "specs" / "MECHANISM_PREREGISTRATION_V1.sha256").read_text(), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_preregistration(copy, seal)


def test_an_unregistered_hypothesis_is_refused() -> None:
    """Choosing the hypothesis after seeing the data is the failure the seal exists to stop."""
    result = certify_mechanism(
        hypothesis_id="CONVENIENT_HYPOTHESIS_INVENTED_LATER",
        candles=random_walk(), event_indices=list(range(200, 3000, 20)),
    )
    assert result["status"] == "NOT_EVALUATED"
    assert result["reason"] == "hypothesis_not_in_sealed_preregistration"


# -- it must be able to say NO ------------------------------------------------


def test_a_random_walk_does_not_produce_a_supported_mechanism() -> None:
    """The single most important test here. Noise must not certify.

    Deliberately run at a powered configuration, so a pass means the statistics
    looked at the data and said no -- not that the harness ran out of samples.
    """
    result = certify_mechanism(
        hypothesis_id="FVG_CONTINUATION_V1", candles=random_walk(POWERED_BARS, seed=11),
        event_indices=POWERED_EVENTS, market="SYNTHETIC", timeframe="15m",
    )
    _assert_reached_a_verdict(result)
    assert result["status"] != "MECHANISM_SUPPORTED"


def test_noise_does_not_certify_across_many_seeds() -> None:
    """One clean seed proves nothing; a false positive rate does."""
    supported = []
    for seed in range(4):
        result = certify_mechanism(
            hypothesis_id="FVG_CONTINUATION_V1",
            candles=random_walk(POWERED_BARS, seed=100 + seed),
            event_indices=POWERED_EVENTS, seed=seed,
        )
        _assert_reached_a_verdict(result)
        if result["status"] == "MECHANISM_SUPPORTED":
            supported.append(seed)
    assert not supported, f"noise certified a mechanism on seeds {supported}"


# -- it must be able to say YES -----------------------------------------------


def test_a_planted_effect_is_detected() -> None:
    """Without this, "not supported" would mean nothing but a blind harness."""
    rng = np.random.default_rng(3)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.4, POWERED_BARS))
    # A self-contained bump per event: rise across 60 bars, then decay back over
    # the remaining 30 before the next event. The rise must outlast the longest
    # horizon (40), or the forward return at that horizon straddles the reversal
    # and the effect changes sign -- which is exactly what an earlier version of
    # this fixture did, and the certifier correctly refused to certify it.
    for index in POWERED_EVENTS:
        rise = min(60, POWERED_BARS - index)
        close[index:index + rise] += np.linspace(0.0, 3.0, rise)
        decay_start = index + 60
        decay = min(30, POWERED_BARS - decay_start)
        if decay > 0:
            close[decay_start:decay_start + decay] += np.linspace(3.0, 0.0, decay)
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=POWERED_BARS, freq="15min", tz="UTC"),
        "open": close, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1.0,
    })
    result = certify_mechanism(
        hypothesis_id="FVG_CONTINUATION_V1", candles=frame, event_indices=POWERED_EVENTS,
    )
    assert result["status"] == "MECHANISM_SUPPORTED", result.get("reason") or result["status"]
    assert all(h["observed_difference"] > 0 for h in result["per_horizon"])


# -- power and refusal --------------------------------------------------------


def test_too_few_events_is_underpowered_not_a_verdict() -> None:
    result = certify_mechanism(
        hypothesis_id="FVG_CONTINUATION_V1", candles=random_walk(), event_indices=[500, 900, 1400],
    )
    assert result["status"] == "UNDERPOWERED"
    assert "below preregistered minimum" in result["reason"]


def test_malformed_candles_are_a_data_failure() -> None:
    result = certify_mechanism(
        hypothesis_id="FVG_CONTINUATION_V1",
        candles=pd.DataFrame({"close": [1.0, 2.0]}), event_indices=list(range(200)),
    )
    assert result["status"] == "DATA_FAILED"


def test_certificate_never_grants_authority() -> None:
    result = certify_mechanism(
        hypothesis_id="FVG_CONTINUATION_V1", candles=random_walk(),
        event_indices=list(range(300, 3000, 15)),
    )
    contract = result["authority_contract"]
    assert contract["signal_allowed"] is False
    assert contract["live_execution_allowed"] is False
    assert contract["human_adjudication_used"] is False
    assert "economic_value" in contract["cannot_prove"]


# -- the statistics -----------------------------------------------------------


def test_block_bootstrap_is_more_conservative_than_ignoring_dependence() -> None:
    """Overlapping windows inflate significance unless the blocks respect them.

    On a serially dependent series, longer blocks must widen the null -- that
    widening IS the correction. If it did not, the block length would be
    decorative and the p-values would be the too-small ones a plain bootstrap
    gives.
    """
    rng = np.random.default_rng(5)
    dependent = pd.Series(rng.normal(0.05, 1, 600)).rolling(20, min_periods=1).mean().to_numpy()
    wide = paired_block_bootstrap(dependent, block_length=20, resamples=600, seed=1)
    narrow = paired_block_bootstrap(dependent, block_length=1, resamples=600, seed=1)
    assert wide["null_std"] > narrow["null_std"]
    assert wide["p_value"] >= narrow["p_value"]


def test_bootstrap_refuses_on_thin_input() -> None:
    assert paired_block_bootstrap(np.array([1.0]), block_length=5)["p_value"] is None


def test_bootstrap_ignores_non_finite_pairs() -> None:
    """An event whose controls all fell outside the data contributes nothing."""
    values = np.array([1.0, np.nan, 1.0, 1.0, np.nan])
    result = paired_block_bootstrap(values, block_length=2, resamples=200, seed=0)
    assert result["paired_observations"] == 3


def test_a_zero_mean_difference_series_is_not_significant() -> None:
    rng = np.random.default_rng(2)
    result = paired_block_bootstrap(rng.normal(0.0, 1.0, 400), block_length=10, resamples=600, seed=3)
    assert result["p_value"] > 0.05


# -- the observable actually registered is the one measured -------------------


def test_an_unimplemented_observable_is_refused_not_substituted() -> None:
    """FVG_FILL_RATE_V1 declares band_touch_within_horizon.

    Before the dispatch existed every hypothesis was scored with forward
    returns, so this one would have been answered with a directional-return
    number and stamped with the fill-rate id -- the wrong question, confidently
    labelled as the right one.
    """
    result = certify_mechanism(
        hypothesis_id="FVG_FILL_RATE_V1", candles=random_walk(POWERED_BARS),
        event_indices=POWERED_EVENTS,
    )
    assert result["status"] == "NOT_EVALUATED"
    assert "band_touch_within_horizon" in result["reason"]


def test_range_expansion_measures_expansion() -> None:
    n = 400
    high = np.concatenate([np.full(200, 100.5), np.full(200, 103.0)])
    low = np.concatenate([np.full(200, 100.0), np.full(200, 100.0)])
    frame = pd.DataFrame({"high": high, "low": low, "close": (high + low) / 2})
    # Range is 0.5 before index 200 and 3.0 after: a six-fold expansion.
    assert realised_range_expansion(frame, [200], horizon=50)[0] == pytest.approx(6.0)


def test_range_expansion_returns_nan_without_room_on_either_side() -> None:
    frame = pd.DataFrame({"high": [1.0] * 60, "low": [0.5] * 60, "close": [0.75] * 60})
    assert np.isnan(realised_range_expansion(frame, [5], horizon=20)[0])
    assert np.isnan(realised_range_expansion(frame, [55], horizon=20)[0])


def test_benjamini_hochberg_step_up() -> None:
    assert benjamini_hochberg([0.001, 0.002, 0.003], 0.05) == [True, True, True]
    assert benjamini_hochberg([0.9, 0.8, 0.7], 0.05) == [False, False, False]
    # Step-up keeps everything below the largest passing rank, not just the smallest p.
    assert benjamini_hochberg([0.01, 0.04, 0.9], 0.05) == [True, False, False]
    assert benjamini_hochberg([None, 0.9], 0.05) == [False, False]


def test_forward_returns_drop_events_without_a_full_horizon() -> None:
    candles = random_walk(n=100)
    # NaN rather than dropped, so a paired design keeps positional alignment.
    assert np.isnan(forward_returns(candles, [95], horizon=20)[0])
    assert np.isfinite(forward_returns(candles, [10], horizon=20)[0])


def test_forward_returns_respect_the_sign_convention() -> None:
    """A bearish event that falls scores positively in its own direction."""
    close = np.linspace(100.0, 90.0, 60)
    frame = pd.DataFrame({"high": close, "low": close, "close": close})
    assert forward_returns(frame, [0], horizon=20, signs=[-1.0])[0] > 0
    assert forward_returns(frame, [0], horizon=20, signs=[1.0])[0] < 0


# -- matched controls ---------------------------------------------------------


def test_controls_never_sit_inside_an_event_outcome_window() -> None:
    """Exclusion is forward-looking: a bar after an event may carry its effect.

    A bar before an event cannot be contaminated by it, so those stay eligible;
    excluding them symmetrically would discard half the usable controls for no
    statistical gain.
    """
    candles = random_walk()
    events = list(range(400, 3000, 90))
    cohort = sample_matched_controls(candles, events, exclusion_bars=20, horizon_bars=20, seed=2)
    assert cohort.control_indices, "expected controls at this event spacing"
    for control in cohort.control_indices:
        for event in events:
            assert not (event - 1 <= control <= event + 20), f"control {control} inside window of {event}"


def test_matching_balances_the_covariates_it_matches_on() -> None:
    candles = random_walk()
    cohort = sample_matched_controls(candles, list(range(400, 3400, 25)), seed=4)
    report = balance_report(candles, cohort)
    assert report["balanced"] is True, report


def test_sampling_is_deterministic_for_a_given_seed() -> None:
    candles = random_walk()
    events = list(range(400, 2000, 30))
    first = sample_matched_controls(candles, events, seed=9).control_indices
    second = sample_matched_controls(candles, events, seed=9).control_indices
    assert first == second


def test_unmatchable_events_are_reported_not_paired_loosely() -> None:
    """Dropping an event costs power; a bad match costs correctness."""
    candles = random_walk(n=300)
    cohort = sample_matched_controls(candles, [290, 295], exclusion_bars=20, horizon_bars=20)
    assert cohort.diagnostics["events_matched"] + cohort.diagnostics["events_unmatched"] == 2


def test_empty_input_is_handled() -> None:
    assert sample_matched_controls(random_walk(), []).samples == ()
