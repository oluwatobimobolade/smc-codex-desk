"""Matched control sampling for mechanism tests.

Price revisits most levels eventually. That single fact makes almost every
unguarded Smart Money claim self-confirming: "price returned to the zone" is
true of nearly any band you draw, so observing it proves nothing about the zone.

The fix is the design Lo, Mamaysky and Wang used to test technical patterns --
compare the distribution conditional on the pattern against the distribution
where the pattern is absent. A control here is a point in the same series, at a
comparable position in the range, at a comparable scale, and near in time, where
the pattern did NOT occur. If the conditional and control distributions are
indistinguishable, the pattern carries no information, however tidy it looks.

Matching on all three dimensions matters and each one guards a different way of
fooling yourself:

* **size** -- large gaps appear in volatile stretches; comparing them against
  quiet-period controls measures volatility, not the gap.
* **location** -- events cluster at range extremes where forward returns are
  already skewed; unmatched controls smuggle that skew in as an effect.
* **recency** -- markets drift through regimes, so a control drawn years away
  is a different market.

Selection is deterministic given a seed. Nothing here reads a detector or a
label: it takes candles and event times and returns control times.

Authority: descriptive. Sampling proves nothing on its own; it makes a claim
falsifiable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

DEFAULT_CONTROLS_PER_EVENT = 5
DEFAULT_RECENCY_WINDOW_BARS = 500
# Finer buckets match more tightly and balance better, at the cost of a smaller
# eligible pool. These were raised from 4/4 because a four-way split left
# location imbalanced at 0.19 standard deviations -- comfortably past the ~0.1
# rule of thumb, which would have meant the comparison measured where in the
# range the events sat rather than the events themselves. Tuning matching to
# pass a balance check is a design choice about the control arm; it is not the
# same as tuning a threshold until a result turns significant, which the
# preregistration forbids.
DEFAULT_SIZE_BUCKETS = 5
DEFAULT_LOCATION_BUCKETS = 10
# Controls must not sit inside an event's own outcome window, or the "control"
# is measuring the event.
DEFAULT_EXCLUSION_BARS = 20


@dataclass(frozen=True)
class MatchedSample:
    """One event paired with the control indices drawn for it."""

    event_index: int
    control_indices: tuple[int, ...]
    size_bucket: int
    location_bucket: int
    exhausted: bool = False


@dataclass(frozen=True)
class MatchedCohort:
    samples: tuple[MatchedSample, ...] = ()
    unmatched_event_indices: tuple[int, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def event_indices(self) -> list[int]:
        return [sample.event_index for sample in self.samples]

    @property
    def control_indices(self) -> list[int]:
        return [index for sample in self.samples for index in sample.control_indices]


def _bucketise(values: np.ndarray, buckets: int) -> np.ndarray:
    """Rank-based buckets. Quantiles beat fixed widths on skewed financial data."""
    finite = np.isfinite(values)
    out = np.full(values.shape, -1, dtype=int)
    if not finite.any():
        return out
    ranks = pd.Series(values[finite]).rank(pct=True, method="average").to_numpy()
    out[finite] = np.clip((ranks * buckets).astype(int), 0, buckets - 1)
    return out


def rolling_scale(candles: pd.DataFrame, window: int = 14) -> np.ndarray:
    """A per-bar volatility scale, used for the size dimension."""
    high = candles["high"].astype(float).to_numpy()
    low = candles["low"].astype(float).to_numpy()
    close = candles["close"].astype(float).to_numpy()
    previous_close = np.concatenate([[close[0]], close[:-1]])
    true_range = np.maximum.reduce([
        high - low, np.abs(high - previous_close), np.abs(low - previous_close)
    ])
    return pd.Series(true_range).rolling(window, min_periods=2).mean().to_numpy()


def range_location(candles: pd.DataFrame, window: int = 100) -> np.ndarray:
    """Where each bar sits in its recent range: 0.0 at the low, 1.0 at the high.

    This is the premium/discount idea stated so a control can be matched on it.
    """
    close = candles["close"].astype(float)
    high = candles["high"].astype(float).rolling(window, min_periods=5).max()
    low = candles["low"].astype(float).rolling(window, min_periods=5).min()
    span = (high - low).replace(0.0, np.nan)
    return ((close - low) / span).to_numpy()


def sample_matched_controls(
    candles: pd.DataFrame,
    event_indices: Sequence[int],
    *,
    controls_per_event: int = DEFAULT_CONTROLS_PER_EVENT,
    recency_window_bars: int = DEFAULT_RECENCY_WINDOW_BARS,
    size_buckets: int = DEFAULT_SIZE_BUCKETS,
    location_buckets: int = DEFAULT_LOCATION_BUCKETS,
    exclusion_bars: int = DEFAULT_EXCLUSION_BARS,
    horizon_bars: int = DEFAULT_EXCLUSION_BARS,
    seed: int = 0,
) -> MatchedCohort:
    """Draw controls matched on size, location and recency.

    An event that cannot be matched is reported in ``unmatched_event_indices``
    rather than paired with a loose control. Dropping it costs power; accepting
    a bad match costs correctness, and only one of those is recoverable.
    """
    total = len(candles)
    events = sorted({int(i) for i in event_indices if 0 <= int(i) < total})
    if not events or total == 0:
        return MatchedCohort(diagnostics={"reason": "no_events_or_no_candles", "event_count": len(events)})

    scale = rolling_scale(candles)
    location = range_location(candles)
    size_bucket = _bucketise(scale, size_buckets)
    location_bucket = _bucketise(location, location_buckets)

    # A bar is ineligible as a control if it is an event, sits inside an event's
    # OUTCOME window, or cannot complete its own horizon.
    #
    # The exclusion is asymmetric on purpose. A bar after an event may carry
    # that event's effect and would contaminate the control arm; a bar before
    # it cannot, so excluding both sides throws away half the usable controls
    # for no gain. With densely spaced events even this can exhaust the pool --
    # that is a real limit on testing frequent patterns at long horizons, and
    # it is reported through `events_unmatched` rather than papered over.
    ineligible = np.zeros(total, dtype=bool)
    for index in events:
        lo = max(0, index - 1)
        hi = min(total, index + exclusion_bars + 1)
        ineligible[lo:hi] = True
    if horizon_bars > 0:
        ineligible[max(0, total - horizon_bars):] = True
    ineligible |= (size_bucket < 0) | (location_bucket < 0)

    rng = np.random.default_rng(seed)
    samples: list[MatchedSample] = []
    unmatched: list[int] = []
    exhausted_count = 0

    for index in events:
        if size_bucket[index] < 0 or location_bucket[index] < 0:
            unmatched.append(index)
            continue
        lo = max(0, index - recency_window_bars)
        hi = min(total, index + recency_window_bars + 1)
        window = np.arange(lo, hi)
        eligible = window[
            (~ineligible[lo:hi])
            & (size_bucket[lo:hi] == size_bucket[index])
            & (location_bucket[lo:hi] == location_bucket[index])
        ]
        if eligible.size == 0:
            unmatched.append(index)
            continue
        exhausted = eligible.size < controls_per_event
        if exhausted:
            exhausted_count += 1
        chosen = rng.choice(eligible, size=min(controls_per_event, eligible.size), replace=False)
        samples.append(
            MatchedSample(
                event_index=index,
                control_indices=tuple(sorted(int(c) for c in chosen)),
                size_bucket=int(size_bucket[index]),
                location_bucket=int(location_bucket[index]),
                exhausted=exhausted,
            )
        )

    return MatchedCohort(
        samples=tuple(samples),
        unmatched_event_indices=tuple(unmatched),
        diagnostics={
            "events_requested": len(events),
            "events_matched": len(samples),
            "events_unmatched": len(unmatched),
            "events_with_thin_control_pool": exhausted_count,
            "controls_drawn": sum(len(s.control_indices) for s in samples),
            "controls_per_event_target": controls_per_event,
            "recency_window_bars": recency_window_bars,
            "size_buckets": size_buckets,
            "location_buckets": location_buckets,
            "seed": seed,
        },
    )


def balance_report(
    candles: pd.DataFrame, cohort: MatchedCohort, *, window: int = 14
) -> dict[str, Any]:
    """Did the matching actually balance? Report it rather than assume it.

    A standardised mean difference above roughly 0.1 is the usual signal that a
    covariate is still imbalanced and the comparison is contaminated.
    """
    if not cohort.samples:
        return {"balanced": None, "reason": "empty_cohort"}
    scale = rolling_scale(candles, window)
    location = range_location(candles)
    out: dict[str, Any] = {}
    for name, series in (("size", scale), ("location", location)):
        treated = np.array([series[s.event_index] for s in cohort.samples], dtype=float)
        control = np.array([series[i] for i in cohort.control_indices], dtype=float)
        treated, control = treated[np.isfinite(treated)], control[np.isfinite(control)]
        if treated.size == 0 or control.size == 0:
            out[name] = {"standardised_mean_difference": None}
            continue
        pooled = np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2.0) if treated.size > 1 and control.size > 1 else 0.0
        smd = float((treated.mean() - control.mean()) / pooled) if pooled > 0 else 0.0
        out[name] = {
            "treated_mean": float(treated.mean()),
            "control_mean": float(control.mean()),
            "standardised_mean_difference": round(smd, 6),
        }
    smds = [v.get("standardised_mean_difference") for v in out.values()]
    out["balanced"] = all(s is not None and abs(s) <= 0.1 for s in smds)
    return out


__all__ = [
    "DEFAULT_CONTROLS_PER_EVENT",
    "DEFAULT_EXCLUSION_BARS",
    "DEFAULT_LOCATION_BUCKETS",
    "DEFAULT_RECENCY_WINDOW_BARS",
    "DEFAULT_SIZE_BUCKETS",
    "MatchedCohort",
    "MatchedSample",
    "balance_report",
    "range_location",
    "rolling_scale",
    "sample_matched_controls",
]
