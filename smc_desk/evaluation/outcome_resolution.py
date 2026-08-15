"""Resolve logged decisions against what the market actually did.

The selective-outcome ledger records what the system decided and the read it
would have taken. Nothing scored those reads, so ``coverage: 0.0`` and a run of
refusals stayed uninterpretable: a system that correctly stays out and a system
that is broken and silent produce identical ledgers until outcomes resolve.

This module is the market's half of that record. It is deliberately *not* an
accuracy claim about SMC: it answers one frozen question per case -- did the
read verify, and was there a tradeable run in that direction -- so that
``missed_favorable_outcome_rate`` becomes a measured number.

The outcome definition is frozen and named. It is recorded on every event so a
later reader can tell which rule produced the verdict, and so that changing the
rule cannot silently restate old results.

Authority: descriptive. Resolution creates no signal, promotes no object, and
never feeds a detector threshold. Under the autonomous truth constitution this
is evidence for the MECHANISM/FORECAST rungs, not for DEFINITION_CONFORMANT.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Mapping

import pandas as pd

from smc_desk.evaluation.selective_outcomes import OutcomeEvent

# Frozen. Changing any of these constants requires a new definition id, because
# results carrying the old id must stay comparable.
FROZEN_OUTCOME_DEFINITION = "triple_barrier_1atr_20bar_close_return_v1"
DEFAULT_HORIZON_BARS = 20
DEFAULT_BARRIER_ATR_MULTIPLE = 1.0
# A close-to-close move smaller than this is not evidence of direction.
NEUTRAL_BAND_ATR_MULTIPLE = 0.25

BarrierHit = Literal["up", "down", "none"]


class LookaheadError(ValueError):
    """Raised when forward data is not strictly after the decision.

    This is the error class the project exists to prevent, and it has been
    introduced here before by treating a candle's open timestamp as if it were
    its close. Resolution refuses rather than silently scoring itself against
    data the decision could have seen.
    """


def _tz_aware(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def first_barrier_hit(
    forward: pd.DataFrame,
    *,
    reference_price: float,
    barrier_distance: float,
) -> BarrierHit:
    """Which symmetric barrier price reached first, bar by bar.

    A bar that spans both barriers is reported as ``none``: intrabar order is
    unknowable from OHLCV, and guessing it is how backtests flatter themselves.
    """
    upper = reference_price + barrier_distance
    lower = reference_price - barrier_distance
    for row in forward.itertuples(index=False):
        touched_up = float(row.high) >= upper
        touched_down = float(row.low) <= lower
        if touched_up and touched_down:
            return "none"
        if touched_up:
            return "up"
        if touched_down:
            return "down"
    return "none"


def resolve_decision_outcome(
    decision: Mapping[str, Any],
    forward: pd.DataFrame,
    *,
    atr: float | None,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
    barrier_atr_multiple: float = DEFAULT_BARRIER_ATR_MULTIPLE,
    resolved_at: datetime | None = None,
    source_hashes: Mapping[str, str] | None = None,
) -> OutcomeEvent:
    """Score one logged DECISION against the candles that followed it.

    ``forward`` must contain only candles that closed strictly after the
    decision time, ordered oldest first, with open/high/low/close columns.
    """
    case_id = str(decision.get("case_id") or "")
    decision_time = _tz_aware(decision.get("decision_time"))
    stamp = resolved_at or datetime.now(timezone.utc)
    hashes = dict(source_hashes or {})

    def event(state: str, **kwargs: Any) -> OutcomeEvent:
        return OutcomeEvent(
            case_id=case_id,
            resolved_at=stamp,
            state=state,  # type: ignore[arg-type]
            outcome_definition=FROZEN_OUTCOME_DEFINITION,
            source_hashes=hashes,
            **kwargs,
        )

    # A run that could not read the market made no judgement to score.
    if str(decision.get("decision") or "") == "DATA_FAILED":
        return event("DATA_FAILED")
    if atr is None or not (atr > 0):
        return event("DATA_FAILED")

    if forward is None or forward.empty:
        return event("UNRESOLVED")
    if not {"high", "low", "close"}.issubset(forward.columns):
        return event("DATA_FAILED")

    if "timestamp" in forward.columns:
        # decision_time is the close of the last seen candle, so the next
        # candle opens exactly at it: equality is legitimate, earlier is a leak.
        earliest = _tz_aware(forward["timestamp"].iloc[0])
        if earliest < decision_time:
            raise LookaheadError(
                f"{case_id}: forward candle opens {earliest.isoformat()}, before the "
                f"decision at {decision_time.isoformat()}"
            )

    # Not enough market has happened yet. Refusing to score is the honest state;
    # scoring a short window would quietly change the frozen horizon.
    if len(forward) < horizon_bars:
        return event("UNRESOLVED")

    window = forward.iloc[:horizon_bars]
    reference_price = float(window["close"].iloc[0])
    if not (reference_price > 0):
        return event("DATA_FAILED")
    final_close = float(window["close"].iloc[-1])

    hit = first_barrier_hit(
        window,
        reference_price=reference_price,
        barrier_distance=atr * barrier_atr_multiple,
    )

    prediction = str(decision.get("shadow_prediction") or "").upper()
    signed_move = final_close - reference_price
    neutral_band = atr * NEUTRAL_BAND_ATR_MULTIPLE

    if prediction == "BULLISH":
        correct = signed_move > neutral_band
        favorable = hit == "up"
        directional_move = signed_move
    elif prediction == "BEARISH":
        correct = signed_move < -neutral_band
        favorable = hit == "down"
        directional_move = -signed_move
    elif prediction == "NEUTRAL":
        # A neutral read verifies by nothing happening, and offers no trade.
        correct = abs(signed_move) <= neutral_band and hit == "none"
        favorable = False
        directional_move = -abs(signed_move)
    else:
        # No recorded read means nothing to score, which is not a market failure.
        return event("UNRESOLVED")

    return event(
        "RESOLVED",
        shadow_prediction_correct=bool(correct),
        favorable_opportunity=bool(favorable),
        outcome_return_bps=round(directional_move / reference_price * 10_000.0, 6),
    )


def forward_window(
    candles: pd.DataFrame,
    *,
    decision_time: Any,
    limit: int | None = None,
) -> pd.DataFrame:
    """Candles that begin at or after ``decision_time``.

    ``decision_time`` is the CLOSE of the last candle the system saw, so the
    next candle opens exactly at it. Admitting a candle whose open is earlier
    would hand the resolver a bar the decision was made inside -- the precise
    leak this project has recorded before -- so the boundary is
    ``open >= decision_time`` and nothing looser.
    """
    if candles is None or candles.empty:
        return candles
    cutoff = _tz_aware(decision_time)
    stamps = pd.to_datetime(candles["timestamp"], utc=True)
    admissible = candles.loc[stamps >= cutoff].reset_index(drop=True)
    return admissible.iloc[:limit] if limit is not None else admissible


__all__ = [
    "DEFAULT_BARRIER_ATR_MULTIPLE",
    "DEFAULT_HORIZON_BARS",
    "FROZEN_OUTCOME_DEFINITION",
    "NEUTRAL_BAND_ATR_MULTIPLE",
    "LookaheadError",
    "first_barrier_hit",
    "forward_window",
    "resolve_decision_outcome",
]
