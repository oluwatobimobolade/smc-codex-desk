"""Multi-timeframe SMC bias and context helpers.

All functions in this module enforce no-future-leakage:
when computing higher-timeframe context for a decision at time `t`,
we only use HTF candles whose close time is at or before `t`.
The 15m slice passed in must be the analyzer-visible history up to
`decision_time` (inclusive of the 15m candle at `decision_time`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .engine import analyze_dataframe, infer_trend
from .models import Direction, HigherTimeframePoi, Zone
from .rules import RuleConfig


TimeframeKey = Literal["1h", "4h", "1d"]


@dataclass
class HtfContext:
    timeframe: str
    candle_count: int
    last_close: float | None
    bias: Literal["bullish", "bearish", "neutral"]
    last_structure_label: str | None
    last_structure_direction: str | None
    last_structure_index: int | None
    inferred_trend: str
    atr: float | None = None
    poi_candidates: list[Zone] = field(default_factory=list)


@dataclass
class MtfSnapshot:
    decision_time: pd.Timestamp
    bars_visible_15m: int
    one_hour: HtfContext
    four_hour: HtfContext
    daily: HtfContext
    alignment: Literal["bullish", "bearish", "neutral"]
    agreement_count: int
    total_count: int
    agreement_ratio: float
    selected_htf_poi: HigherTimeframePoi | None = None


def derive_htf_consensus_bias(snapshot: MtfSnapshot | dict) -> Direction:
    """Return the HTF bias that is safe to feed into execution analysis.

    Consensus rule:
    - 1H and 4H must agree bullish/bearish.
    - 1D may agree or be neutral.
    - If 1D actively opposes 1H/4H, stand aside.
    """
    if isinstance(snapshot, MtfSnapshot):
        one_hour = snapshot.one_hour.bias
        four_hour = snapshot.four_hour.bias
        daily = snapshot.daily.bias
    else:
        one_hour = snapshot["1h"]["bias"]
        four_hour = snapshot["4h"]["bias"]
        daily = snapshot["1d"]["bias"]

    if one_hour not in {"bullish", "bearish"} or four_hour != one_hour:
        return "neutral"
    if daily in {"bullish", "bearish"} and daily != one_hour:
        return "neutral"
    return one_hour


TF_TO_PANDAS_RULE: dict[TimeframeKey, str] = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}

TF_TO_DURATION: dict[TimeframeKey, pd.Timedelta] = {
    "15m": pd.Timedelta("15min"),
    "1h": pd.Timedelta("1h"),
    "4h": pd.Timedelta("4h"),
    "1d": pd.Timedelta("1D"),
}


def slice_15m_to(df: pd.DataFrame, decision_time: pd.Timestamp) -> pd.DataFrame:
    """Return the 15m slice visible to the analyzer at `decision_time`.

    Only candles that have fully closed by `decision_time` are included.
    A candle at T with period D is visible only when T + D <= decision_time.
    """
    timestamps = pd.to_datetime(df["timestamp"], utc=False)
    close_times = timestamps + TF_TO_DURATION["15m"]
    mask = close_times <= decision_time
    return df.loc[mask].reset_index(drop=True)


def resample_ohlcv(df: pd.DataFrame, target_tf: TimeframeKey, decision_time: pd.Timestamp) -> pd.DataFrame:
    """Resample visible 15m history to a higher timeframe without future leakage.

    Only HTF candles whose close time is at or before `decision_time`
    are kept. The current in-progress HTF candle is always dropped.
    Implementation: precompute the full HTF series and slice to drop all
    in-progress candles (matches the precomputed path used during replay).
    """
    if target_tf not in TF_TO_PANDAS_RULE:
        raise ValueError(f"Unsupported target timeframe: {target_tf}")

    if df.empty:
        return df.copy()

    precomputed = precompute_htf_series(df)
    return slice_precomputed_htf(precomputed[target_tf], target_tf, decision_time)


def precompute_htf_series(df_15m: pd.DataFrame) -> dict[TimeframeKey, pd.DataFrame]:
    """Resample the full 15m history to each HTF, preserving full data.

    Exchange 15m timestamps are candle OPENS (candle at 00:00 covers
    00:00-00:15).  We resample with label='left', closed='left' so that
    each HTF bucket covers [T, T+duration) — e.g. a 1H bucket labeled
    00:00 contains candles at 00:00, 00:15, 00:30, 00:45.

    The result for each timeframe is a complete OHLCV dataframe labeled
    by the candle open time. Use ``slice_precomputed_htf`` at decision
    time to drop any in-progress candles for the current decision.
    """
    if df_15m.empty:
        return {tf: df_15m.copy() for tf in TF_TO_PANDAS_RULE}

    indexed = df_15m.assign(_ts=pd.to_datetime(df_15m["timestamp"], utc=False)).set_index("_ts")
    result: dict[TimeframeKey, pd.DataFrame] = {}
    for tf, rule in TF_TO_PANDAS_RULE.items():
        resampled = indexed.resample(rule, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])
        resampled = resampled.reset_index().rename(columns={"_ts": "timestamp"})
        resampled["_close_visible_at"] = pd.to_datetime(resampled["timestamp"], utc=False) + TF_TO_DURATION[tf]
        result[tf] = resampled
    return result


def slice_precomputed_htf(htf_df: pd.DataFrame, target_tf: TimeframeKey, decision_time: pd.Timestamp) -> pd.DataFrame:
    """Return HTF candles whose close time is at or before `decision_time`.

    A HTF candle is visible at decision time `t` only if it fully closed
    at or before `t` (close_time <= decision_time). In-progress candles
    whose close time is in the future relative to `t` are dropped.
    """
    if htf_df.empty:
        return htf_df
    duration = TF_TO_DURATION[target_tf]
    if "_close_visible_at" in htf_df.columns:
        close_times = htf_df["_close_visible_at"]
    else:
        close_times = pd.to_datetime(htf_df["timestamp"], utc=False) + duration
    visible = htf_df.loc[close_times <= decision_time].reset_index(drop=True)
    return visible


def _context_for(
    target_tf: TimeframeKey,
    htf_df: pd.DataFrame,
    decision_time: pd.Timestamp,
    config: RuleConfig,
) -> HtfContext:
    if htf_df.empty or len(htf_df) < 5:
        return HtfContext(
            timeframe=target_tf,
            candle_count=int(len(htf_df)),
            last_close=float(htf_df["close"].iloc[-1]) if not htf_df.empty else None,
            bias="neutral",
            last_structure_label=None,
            last_structure_direction=None,
            last_structure_index=None,
            inferred_trend="neutral",
        )

    htf_df = htf_df.copy()
    htf_df["timestamp"] = pd.to_datetime(htf_df["timestamp"], utc=False)
    analysis, _ = analyze_dataframe(
        df=htf_df,
        symbol="MTF",
        timeframe=target_tf,
        config=config,
        bias_hint=None,
        notes="htf context slice",
        input_type="ohlcv",
    )
    structure_events = [
        event
        for event in analysis.events
        if event.label in {"BOS", "CHoCH"} and event.structure_scope in {"swing", "external", "unknown"}
    ]
    last_event = structure_events[-1] if structure_events else None
    inferred = infer_trend(analysis.swings)
    if last_event:
        bias = last_event.direction if last_event.direction in {"bullish", "bearish"} else inferred
    else:
        bias = inferred
    true_range = pd.concat(
        [
            htf_df["high"] - htf_df["low"],
            (htf_df["high"] - htf_df["close"].shift(1)).abs(),
            (htf_df["low"] - htf_df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(true_range.tail(config.atr_lookback).mean()) if not true_range.empty else None
    allowed_statuses = {"fresh"} if config.require_fresh_poi else {"fresh", "partial"}
    allowed_kinds = set(config.allowed_poi_kinds or ["fvg", "order_block"])
    poi_candidates = [
        zone
        for zone in analysis.zones
        if zone.kind in allowed_kinds and zone.status in allowed_statuses
    ]
    return HtfContext(
        timeframe=target_tf,
        candle_count=int(len(htf_df)),
        last_close=float(htf_df["close"].iloc[-1]),
        bias=bias if bias in {"bullish", "bearish", "neutral"} else "neutral",
        last_structure_label=last_event.label if last_event else None,
        last_structure_direction=last_event.direction if last_event else None,
        last_structure_index=last_event.index if last_event else None,
        inferred_trend=inferred,
        atr=round(atr, 8) if atr is not None else None,
        poi_candidates=poi_candidates,
    )


def _htf_poi_age_bars(context: HtfContext, zone: Zone) -> int:
    if zone.end_index is None:
        return context.candle_count
    return max(0, context.candle_count - 1 - zone.end_index)


def _approach_is_aligned(
    closes: pd.Series,
    direction: Direction,
    lookback: int,
) -> bool:
    if direction not in {"bullish", "bearish"} or len(closes) <= lookback:
        return False
    current = float(closes.iloc[-1])
    prior = float(closes.iloc[-1 - lookback])
    return (direction == "bearish" and current > prior) or (direction == "bullish" and current < prior)


def select_htf_poi(
    snapshot: MtfSnapshot,
    current_price: float,
    config: RuleConfig,
    recent_15m_closes: pd.Series | None = None,
) -> HigherTimeframePoi | None:
    """Choose one aligned 1H/4H POI for monitoring, not for direct execution.

    A zone may be mapped while distant. It becomes ``approaching`` only when
    price is moving toward it and within a timeframe-normalised distance. This
    prevents every untouched historical zone from becoming a live watch alert.
    """
    direction = derive_htf_consensus_bias(snapshot)
    if direction not in {"bullish", "bearish"}:
        return None

    max_age_hours = config.max_zone_age_bars * 0.25
    closes = recent_15m_closes if recent_15m_closes is not None else pd.Series(dtype=float)
    approach_confirmed = _approach_is_aligned(closes, direction, config.htf_approach_lookback_bars)
    candidates: list[HigherTimeframePoi] = []

    for timeframe, context, hours_per_bar in (
        ("1h", snapshot.one_hour, 1.0),
        ("4h", snapshot.four_hour, 4.0),
    ):
        timeframe_atr = context.atr
        if timeframe_atr is None or timeframe_atr <= 0:
            continue
        for zone in context.poi_candidates:
            if zone.direction != direction:
                continue
            age_bars = _htf_poi_age_bars(context, zone)
            if age_bars * hours_per_bar > max_age_hours:
                continue
            if direction == "bearish" and zone.high < current_price:
                continue
            if direction == "bullish" and zone.low > current_price:
                continue

            if zone.low <= current_price <= zone.high:
                state = "at_poi"
                distance_atr = 0.0
            else:
                distance = zone.low - current_price if direction == "bearish" else current_price - zone.high
                distance_atr = max(0.0, distance / timeframe_atr)
                state = (
                    "approaching"
                    if approach_confirmed and distance_atr <= config.htf_poi_watch_distance_atr
                    else "mapped"
                )

            timeframe_bonus = 0.07 if timeframe == "4h" else 0.03
            freshness_bonus = 0.08 if zone.status == "fresh" else 0.02
            distance_penalty = min(0.25, distance_atr * 0.035)
            rank = max(0.0, min(1.0, zone.score + timeframe_bonus + freshness_bonus - distance_penalty))
            candidates.append(
                HigherTimeframePoi(
                    timeframe=timeframe,
                    zone=zone,
                    state=state,
                    distance_atr=round(distance_atr, 3),
                    age_bars=age_bars,
                    rank=round(rank, 3),
                    approach_confirmed=approach_confirmed,
                )
            )

    if not candidates:
        return None
    state_priority = {"mapped": 0, "approaching": 1, "at_poi": 2}
    return sorted(candidates, key=lambda poi: (state_priority[poi.state], poi.rank), reverse=True)[0]


def build_mtf_snapshot(
    df_15m: pd.DataFrame,
    decision_time: pd.Timestamp,
    config: RuleConfig,
    timeframes: tuple[TimeframeKey, ...] = ("1h", "4h", "1d"),
    precomputed: dict[TimeframeKey, pd.DataFrame] | None = None,
) -> MtfSnapshot:
    """Compute the full HTF context at a single decision timestamp."""
    visible_15m = slice_15m_to(df_15m, decision_time)
    contexts: dict[TimeframeKey, HtfContext] = {}
    for tf in timeframes:
        if precomputed is not None and tf in precomputed:
            htf_slice = slice_precomputed_htf(precomputed[tf], tf, decision_time)
        else:
            htf_slice = resample_ohlcv(visible_15m, tf, decision_time)
        contexts[tf] = _context_for(tf, htf_slice, decision_time, config)

    biases = [contexts[tf].bias for tf in timeframes]
    agreement_bullish = sum(1 for bias in biases if bias == "bullish")
    agreement_bearish = sum(1 for bias in biases if bias == "bearish")
    if agreement_bullish == len(biases):
        alignment = "bullish"
    elif agreement_bearish == len(biases):
        alignment = "bearish"
    elif agreement_bullish >= agreement_bearish and agreement_bullish > 0:
        alignment = "bullish"
    elif agreement_bearish > agreement_bullish:
        alignment = "bearish"
    else:
        alignment = "neutral"
    total = len(biases)
    agreement_count = max(agreement_bullish, agreement_bearish)

    snapshot = MtfSnapshot(
        decision_time=pd.Timestamp(decision_time),
        bars_visible_15m=int(len(visible_15m)),
        one_hour=contexts["1h"],
        four_hour=contexts["4h"],
        daily=contexts["1d"],
        alignment=alignment,  # type: ignore[arg-type]
        agreement_count=int(agreement_count),
        total_count=int(total),
        agreement_ratio=round(agreement_count / total, 4) if total else 0.0,
    )
    current_price = float(visible_15m["close"].iloc[-1]) if not visible_15m.empty else 0.0
    snapshot.selected_htf_poi = select_htf_poi(
        snapshot,
        current_price=current_price,
        config=config,
        recent_15m_closes=visible_15m["close"],
    )
    return snapshot


def snapshot_to_dict(snapshot: MtfSnapshot) -> dict:
    def ctx_dict(ctx: HtfContext) -> dict:
        return {
            "timeframe": ctx.timeframe,
            "candle_count": ctx.candle_count,
            "last_close": ctx.last_close,
            "bias": ctx.bias,
            "last_structure_label": ctx.last_structure_label,
            "last_structure_direction": ctx.last_structure_direction,
            "last_structure_index": ctx.last_structure_index,
            "inferred_trend": ctx.inferred_trend,
            "atr": ctx.atr,
            "poi_candidates": [zone.model_dump() for zone in ctx.poi_candidates],
        }

    return {
        "decision_time": pd.Timestamp(snapshot.decision_time).isoformat(),
        "bars_visible_15m": snapshot.bars_visible_15m,
        "1h": ctx_dict(snapshot.one_hour),
        "4h": ctx_dict(snapshot.four_hour),
        "1d": ctx_dict(snapshot.daily),
        "alignment": snapshot.alignment,
        "agreement_count": snapshot.agreement_count,
        "total_count": snapshot.total_count,
        "agreement_ratio": snapshot.agreement_ratio,
        # ``alignment`` is a descriptive plurality across the three HTFs.
        # Execution must use the stricter 1H/4H(+1D) consensus rule instead.
        "execution_consensus": derive_htf_consensus_bias(snapshot),
        "selected_htf_poi": snapshot.selected_htf_poi.model_dump() if snapshot.selected_htf_poi else None,
    }
