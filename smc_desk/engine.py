from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .models import AnalysisResult, HigherTimeframePoi, StructureEvent, StructureScope, SwingPoint, TradePlan, Zone
from .rules import RuleConfig
from .session import summarize_session_context


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    csv_path = Path(path)
    df = pd.read_csv(csv_path)
    df.columns = [column.strip().lower() for column in df.columns]
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    df = df.sort_values("timestamp").dropna(subset=["timestamp"]).reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def _ts_iso(df: pd.DataFrame) -> list[str]:
    """Precompute ISO timestamps once (per-row .isoformat() via df.at is a hot spot)."""
    return [t.isoformat() for t in df["timestamp"]]


def _rolling_prev_mean(x: np.ndarray, lookback: int = 20) -> np.ndarray:
    """out[i] = mean(x[max(0,i-lookback):i]); for i==0 use x[0]; floored at 1e-9.

    Vectorized equivalent of the old per-index ``_avg_body``/``_avg_range`` which
    averaged the ``lookback`` bars *before* index i (exclusive of i).
    """
    n = x.shape[0]
    out = np.empty(n, dtype=float)
    for i in range(n):
        left = max(0, i - lookback)
        seg = x[left:i] if i > left else x[:1]   # i==0 -> x[:1], matches df.iloc[:1]
        out[i] = seg.mean()                        # numpy mean == pandas mean (bit-identical)
    return np.maximum(out, 1e-9)


def detect_swings(df: pd.DataFrame, config: RuleConfig, pivot_window: int | None = None) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    # Use specified window, or fallback to the local_pivot_window
    window = pivot_window or config.swing_scales.local
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    ts = _ts_iso(df)
    for index in range(window, len(df) - window):
        a, b = index - window, index + window + 1
        high = h[index]
        low = l[index]
        if high >= h[a:b].max():
            swings.append(SwingPoint(kind="high", index=index, timestamp=ts[index], price=float(high)))
        if low <= l[a:b].min():
            swings.append(SwingPoint(kind="low", index=index, timestamp=ts[index], price=float(low)))
    swings.sort(key=lambda point: point.index)
    return swings


def _scope_pivot_window(config: RuleConfig, structure_scope: StructureScope) -> int:
    if structure_scope == "internal":
        return config.swing_scales.internal
    elif structure_scope == "swing":
        return config.swing_scales.external
    return config.swing_scales.local


def _recent_swings(swings: list[SwingPoint], kind: str, limit: int = 6) -> list[SwingPoint]:
    return [swing for swing in swings if swing.kind == kind][-limit:]


def _avg_body(df: pd.DataFrame, index: int, lookback: int = 20) -> float:
    left = max(0, index - lookback)
    sample = df.iloc[left:index]
    if sample.empty:
        sample = df.iloc[: index + 1]
    bodies = (sample["close"] - sample["open"]).abs()
    return max(float(bodies.mean()), 1e-9)


def _avg_range(df: pd.DataFrame, index: int, lookback: int = 20) -> float:
    left = max(0, index - lookback)
    sample = df.iloc[left:index]
    if sample.empty:
        sample = df.iloc[: index + 1]
    ranges = sample["high"] - sample["low"]
    return max(float(ranges.mean()), 1e-9)


def _atr(df: pd.DataFrame, lookback: int = 14) -> float:
    sample = df.tail(min(lookback + 1, len(df))).copy()
    if sample.empty:
        return 0.0
    prev_close = sample["close"].shift(1)
    true_range = pd.concat(
        [
            sample["high"] - sample["low"],
            (sample["high"] - prev_close).abs(),
            (sample["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return max(float(true_range.tail(min(lookback, len(true_range))).mean()), 1e-9)


def _displacement_score(df: pd.DataFrame, index: int) -> float:
    body = abs(float(df.at[index, "close"] - df.at[index, "open"]))
    return body / _avg_body(df, index)


def _is_displacement(df: pd.DataFrame, index: int, config: RuleConfig, factor: float | None = None) -> bool:
    threshold = factor if factor is not None else config.displacement_body_factor
    body_score = _displacement_score(df, index)
    range_score = float(df.at[index, "high"] - df.at[index, "low"]) / _avg_range(df, index)
    return body_score >= threshold and range_score >= 0.9


def _event_strength(displacement_score: float, config: RuleConfig) -> str:
    if displacement_score >= config.displacement_body_factor * 1.65:
        return "strong"
    if displacement_score >= config.displacement_body_factor:
        return "valid"
    return "weak"


def infer_trend(swings: list[SwingPoint]) -> str:
    highs = _recent_swings(swings, "high", 2)
    lows = _recent_swings(swings, "low", 2)
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
            return "bullish"
        if highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
            return "bearish"
    return "neutral"


def detect_equal_levels(swings: list[SwingPoint], config: RuleConfig) -> list[Zone]:
    liquidity_zones: list[Zone] = []
    for kind in ("high", "low"):
        points = [swing for swing in swings if swing.kind == kind][-24:]
        if len(points) < config.equal_level_min_touches:
            continue
        points = sorted(points, key=lambda point: point.price)
        clusters: list[list[SwingPoint]] = []
        active: list[SwingPoint] = []
        for point in points:
            if not active:
                active = [point]
                continue
            anchor = float(np.mean([item.price for item in active]))
            tolerance = anchor * (config.equal_level_tolerance_bps / 10000.0)
            if abs(point.price - anchor) <= tolerance:
                active.append(point)
            else:
                clusters.append(active)
                active = [point]
        if active:
            clusters.append(active)

        for cluster in clusters:
            if len(cluster) < config.equal_level_min_touches:
                continue
            cluster = sorted(cluster, key=lambda point: point.index)
            low = min(point.price for point in cluster)
            high = max(point.price for point in cluster)
            label = "Equal Highs" if kind == "high" else "Equal Lows"
            direction = "bearish" if kind == "high" else "bullish"
            touch_bonus = min(0.18, 0.04 * (len(cluster) - config.equal_level_min_touches))
            score = min(0.88, 0.68 + touch_bonus)
            liquidity_zones.append(
                Zone(
                    label=label,
                    kind="liquidity",
                    direction=direction,
                    low=low,
                    high=high,
                    start_index=cluster[0].index,
                    end_index=cluster[-1].index,
                    confidence=score,
                    score=score,
                    status="fresh",
                    touched_count=len(cluster),
                    reason=f"{label} clustered from {len(cluster)} swing touches within tolerance.",
                )
            )
    liquidity_zones.sort(key=lambda zone: (zone.end_index or 0, zone.score), reverse=True)
    return liquidity_zones[:10]


def detect_fvgs(df: pd.DataFrame, config: RuleConfig) -> list[Zone]:
    fvgs: list[Zone] = []
    n = len(df)
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    body = np.abs(c - o)
    rng = h - l
    avg_body = _rolling_prev_mean(body)
    avg_range = _rolling_prev_mean(rng)
    disp = body / avg_body
    for index in range(2, n):
        middle_index = index - 1
        bullish_gap = float(l[index] - h[index - 2])
        bearish_gap = float(l[index - 2] - h[index])
        price_anchor = max(float(c[index]), 1e-9)
        has_impulse = (disp[middle_index] >= config.fvg.displacement_factor
                       and (rng[middle_index] / avg_range[middle_index]) >= 0.9)
        disp_mid = float(disp[middle_index])
        if bullish_gap / price_anchor >= (config.fvg.minimum_gap_bps / 10000.0) and has_impulse:
            low = float(h[index - 2])
            high = float(l[index])
            mitigation_pct = 0.0
            status = "fresh"
            if index + 1 < n:
                min_future = float(l[index + 1 :].min())
                if min_future <= low:
                    mitigation_pct = 1.0
                    status = "mitigated"
                elif min_future < high:
                    mitigation_pct = (high - min_future) / max(high - low, 1e-9)
                    status = "partial"
            score = 0.58 + min(0.22, disp_mid / 10.0) + (0.08 if status == "fresh" else 0.0)
            fvgs.append(
                Zone(
                    label="Bullish FVG",
                    kind="fvg",
                    direction="bullish",
                    low=low,
                    high=high,
                    start_index=index - 2,
                    end_index=index,
                    confidence=min(score, 0.9),
                    score=min(score, 0.9),
                    status=status,
                    mitigation_pct=round(mitigation_pct, 3),
                    reason=f"Three-candle bullish imbalance with displacement score {disp_mid:.2f}.",
                )
            )
        if bearish_gap / price_anchor >= (config.fvg.minimum_gap_bps / 10000.0) and has_impulse:
            low = float(h[index])
            high = float(l[index - 2])
            mitigation_pct = 0.0
            status = "fresh"
            if index + 1 < n:
                max_future = float(h[index + 1 :].max())
                if max_future >= high:
                    mitigation_pct = 1.0
                    status = "mitigated"
                elif max_future > low:
                    mitigation_pct = (max_future - low) / max(high - low, 1e-9)
                    status = "partial"
            score = 0.58 + min(0.22, disp_mid / 10.0) + (0.08 if status == "fresh" else 0.0)
            fvgs.append(
                Zone(
                    label="Bearish FVG",
                    kind="fvg",
                    direction="bearish",
                    low=low,
                    high=high,
                    start_index=index - 2,
                    end_index=index,
                    confidence=min(score, 0.9),
                    score=min(score, 0.9),
                    status=status,
                    mitigation_pct=round(mitigation_pct, 3),
                    reason=f"Three-candle bearish imbalance with displacement score {disp_mid:.2f}.",
                )
            )
    return fvgs[-10:]


def detect_structure_events(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    config: RuleConfig,
    structure_scope: StructureScope = "swing",
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    swing_highs = [swing for swing in swings if swing.kind == "high"]
    swing_lows = [swing for swing in swings if swing.kind == "low"]
    high_cursor = 0
    low_cursor = 0
    active_high: SwingPoint | None = None
    active_low: SwingPoint | None = None
    protected_high: SwingPoint | None = None
    protected_low: SwingPoint | None = None
    trend = "neutral"
    broken_high_indices: set[int] = set()
    broken_low_indices: set[int] = set()
    requires_protected_reversal = structure_scope in {"swing", "external"}

    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    body = np.abs(c - o)
    rng = h - l
    avg_body = _rolling_prev_mean(body)
    avg_range = _rolling_prev_mean(rng)
    disp = body / avg_body
    ts = _ts_iso(df)

    for index in range(len(df)):
        while high_cursor < len(swing_highs) and swing_highs[high_cursor].index < index:
            active_high = swing_highs[high_cursor]
            high_cursor += 1
        while low_cursor < len(swing_lows) and swing_lows[low_cursor].index < index:
            active_low = swing_lows[low_cursor]
            low_cursor += 1

        close = float(c[index])
        timestamp = ts[index]

        high_to_break = protected_high if requires_protected_reversal and trend == "bearish" and protected_high else active_high
        is_protected_high_break = bool(trend == "bearish" and protected_high and high_to_break == protected_high)
        if high_to_break and (is_protected_high_break or high_to_break.index not in broken_high_indices):
            threshold = high_to_break.price * (1.0 + config.structure_break_min_bps / 10000.0)
            displacement_score = float(disp[index])
            meets_displacement = not config.break_confirmation.displacement_required or (disp[index] >= config.displacement_body_factor and (rng[index] / avg_range[index]) >= 0.9)
            if close > threshold and meets_displacement:
                label = "BOS" if trend in {"neutral", "bullish"} else "CHoCH"
                protected_word = "protected " if is_protected_high_break and requires_protected_reversal else ""
                internal_word = "internal " if structure_scope == "internal" else ""
                reason = f"Close broke {protected_word}{internal_word}swing high at {high_to_break.price:.4f}."
                events.append(
                    StructureEvent(
                        label=label,
                        direction="bullish",
                        index=index,
                        timestamp=timestamp,
                        price=close,
                        reason=reason,
                        structure_scope=structure_scope,
                        broken_level=high_to_break.price,
                        displacement_score=round(displacement_score, 3),
                        strength=_event_strength(displacement_score, config),  # type: ignore[arg-type]
                    )
                )
                broken_high_indices.add(high_to_break.index)
                trend = "bullish"
                protected_low = active_low

        low_to_break = protected_low if requires_protected_reversal and trend == "bullish" and protected_low else active_low
        is_protected_low_break = bool(trend == "bullish" and protected_low and low_to_break == protected_low)
        if low_to_break and (is_protected_low_break or low_to_break.index not in broken_low_indices):
            threshold = low_to_break.price * (1.0 - config.structure_break_min_bps / 10000.0)
            displacement_score = float(disp[index])
            meets_displacement = not config.break_confirmation.displacement_required or (disp[index] >= config.displacement_body_factor and (rng[index] / avg_range[index]) >= 0.9)
            if close < threshold and meets_displacement:
                label = "BOS" if trend in {"neutral", "bearish"} else "CHoCH"
                protected_word = "protected " if is_protected_low_break and requires_protected_reversal else ""
                internal_word = "internal " if structure_scope == "internal" else ""
                reason = f"Close broke {protected_word}{internal_word}swing low at {low_to_break.price:.4f}."
                events.append(
                    StructureEvent(
                        label=label,
                        direction="bearish",
                        index=index,
                        timestamp=timestamp,
                        price=close,
                        reason=reason,
                        structure_scope=structure_scope,
                        broken_level=low_to_break.price,
                        displacement_score=round(displacement_score, 3),
                        strength=_event_strength(displacement_score, config),  # type: ignore[arg-type]
                    )
                )
                broken_low_indices.add(low_to_break.index)
                trend = "bearish"
                protected_high = active_high

    return events[-12:]


def _merge_structure_events(swing_events: list[StructureEvent], internal_events: list[StructureEvent]) -> list[StructureEvent]:
    merged: list[StructureEvent] = []
    seen: set[tuple[int, str, str, float | None]] = set()
    for event in sorted(swing_events + internal_events, key=lambda item: (item.index, item.structure_scope != "swing")):
        key = (event.index, event.label, event.direction, event.broken_level)
        if key in seen:
            continue
        merged.append(event)
        seen.add(key)
    return merged


def detect_liquidity_sweeps(df: pd.DataFrame, swings: list[SwingPoint], config: RuleConfig) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    recent_swings = swings[-config.liquidity_sweep_lookback :]
    o = df["open"].to_numpy(dtype=float)
    h_arr = df["high"].to_numpy(dtype=float)
    l_arr = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    disp = np.abs(c - o) / _rolling_prev_mean(np.abs(c - o))
    ts = _ts_iso(df)
    for index in range(len(df)):
        prior_highs = [swing for swing in recent_swings if swing.kind == "high" and swing.index < index]
        prior_lows = [swing for swing in recent_swings if swing.kind == "low" and swing.index < index]
        timestamp = ts[index]
        high = float(h_arr[index])
        low = float(l_arr[index])
        close = float(c[index])

        if prior_highs:
            level = prior_highs[-1].price
            if high > level * (1.0 + config.structure_break_min_bps / 20000.0) and close < level:
                events.append(
                    StructureEvent(
                        label="Liquidity Sweep",
                        direction="bearish",
                        index=index,
                        timestamp=timestamp,
                        price=close,
                        swept_level=level,
                        displacement_score=round(float(disp[index]), 3),
                        strength=_event_strength(float(disp[index]), config),  # type: ignore[arg-type]
                        reason=f"Buy-side liquidity swept above {level:.4f} and candle closed back below.",
                    )
                )
        if prior_lows:
            level = prior_lows[-1].price
            if low < level * (1.0 - config.structure_break_min_bps / 20000.0) and close > level:
                events.append(
                    StructureEvent(
                        label="Liquidity Sweep",
                        direction="bullish",
                        index=index,
                        timestamp=timestamp,
                        price=close,
                        swept_level=level,
                        displacement_score=round(float(disp[index]), 3),
                        strength=_event_strength(float(disp[index]), config),  # type: ignore[arg-type]
                        reason=f"Sell-side liquidity swept below {level:.4f} and candle closed back above.",
                    )
                )
    deduped: list[StructureEvent] = []
    seen: set[tuple[int, str, float | None]] = set()
    for event in events:
        key = (event.index, event.direction, event.swept_level)
        if key not in seen:
            deduped.append(event)
            seen.add(key)
    return deduped[-12:]


def _last_significant_ob_candle(opposite: pd.DataFrame, df: pd.DataFrame, config: RuleConfig) -> int | None:
    """Most recent opposite-color candle whose body clears the OB floor.

    Thesis [CONTESTED resolution]: the order block is the last *significant* opposite
    candle before displacement, not the literal last opposite candle (often a tiny doji
    that hides the real OB). Returns the df index label, or None if none clear the floor.
    """
    for candle_index in reversed(opposite.index.tolist()):
        body_factor = abs(float(df.at[candle_index, "close"] - df.at[candle_index, "open"])) / _avg_body(df, candle_index)
        if body_factor >= config.ob_min_body_factor:
            return int(candle_index)
    return None


def detect_order_blocks(df: pd.DataFrame, events: list[StructureEvent], config: RuleConfig) -> list[Zone]:
    order_blocks: list[Zone] = []
    for event in events[-8:]:
        if event.label not in {"BOS", "CHoCH"} or event.strength == "weak":
            continue
        window_start = max(0, event.index - config.ob_lookback)
        pre_event = df.iloc[window_start : event.index]
        if pre_event.empty:
            continue

        if event.direction == "bullish":
            opposite = pre_event[pre_event["close"] < pre_event["open"]]
            candle_index = _last_significant_ob_candle(opposite, df, config)
            if candle_index is None:
                continue
            candle = df.loc[candle_index]
            body_factor = abs(float(candle["close"] - candle["open"])) / _avg_body(df, candle_index)
            future_lows = df["low"].iloc[candle_index + 1 :]
            status = "fresh"
            mitigation_pct = 0.0
            if not future_lows.empty:
                if float(future_lows.min()) <= float(candle["low"]):
                    status = "mitigated"
                    mitigation_pct = 1.0
                elif float(future_lows.min()) <= float(candle["high"]):
                    status = "partial"
                    mitigation_pct = (float(candle["high"]) - float(future_lows.min())) / max(float(candle["high"] - candle["low"]), 1e-9)
            score = 0.52 + min(0.2, body_factor / 10.0) + min(0.2, event.displacement_score / 10.0) + (0.08 if status == "fresh" else 0.0)
            order_blocks.append(
                Zone(
                    label="Bullish Order Block",
                    kind="order_block",
                    direction="bullish",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    start_index=candle_index,
                    end_index=event.index,
                    confidence=min(score, 0.92),
                    score=min(score, 0.92),
                    status=status,
                    mitigation_pct=round(mitigation_pct, 3),
                    source_event_index=event.index,
                    reason=f"Last bearish candle before {event.label} with displacement score {event.displacement_score:.2f}.",
                )
            )
        else:
            opposite = pre_event[pre_event["close"] > pre_event["open"]]
            candle_index = _last_significant_ob_candle(opposite, df, config)
            if candle_index is None:
                continue
            candle = df.loc[candle_index]
            body_factor = abs(float(candle["close"] - candle["open"])) / _avg_body(df, candle_index)
            future_highs = df["high"].iloc[candle_index + 1 :]
            status = "fresh"
            mitigation_pct = 0.0
            if not future_highs.empty:
                if float(future_highs.max()) >= float(candle["high"]):
                    status = "mitigated"
                    mitigation_pct = 1.0
                elif float(future_highs.max()) >= float(candle["low"]):
                    status = "partial"
                    mitigation_pct = (float(future_highs.max()) - float(candle["low"])) / max(float(candle["high"] - candle["low"]), 1e-9)
            score = 0.52 + min(0.2, body_factor / 10.0) + min(0.2, event.displacement_score / 10.0) + (0.08 if status == "fresh" else 0.0)
            order_blocks.append(
                Zone(
                    label="Bearish Order Block",
                    kind="order_block",
                    direction="bearish",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    start_index=candle_index,
                    end_index=event.index,
                    confidence=min(score, 0.92),
                    score=min(score, 0.92),
                    status=status,
                    mitigation_pct=round(mitigation_pct, 3),
                    source_event_index=event.index,
                    reason=f"Last bullish candle before {event.label} with displacement score {event.displacement_score:.2f}.",
                )
            )
    return order_blocks[-8:]


def _select_range(df: pd.DataFrame, swings: list[SwingPoint]) -> tuple[float, float]:
    if len(swings) >= 4:
        recent = swings[-8:]
        return min(point.price for point in recent), max(point.price for point in recent)
    recent_slice = df.tail(min(50, len(df)))
    return float(recent_slice["low"].min()), float(recent_slice["high"].max())


def _build_trade_plan_for_direction(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    zones: list[Zone],
    events: list[StructureEvent],
    config: RuleConfig,
    direction: str,
    bias_hint: str | None = None,
    poi_selection: str = "balanced",
    htf_poi: HigherTimeframePoi | None = None,
) -> TradePlan:
    """Build a TradePlan for an explicit direction.

    This is the direction-agnostic core previously inside build_trade_plan().
    All prices (POI, stop, target) are derived from engine-computed levels.
    """
    current_close = float(df["close"].iloc[-1])
    range_low, range_high = _select_range(df, swings)
    midpoint = (range_low + range_high) / 2.0
    structure_events = [event for event in events if event.label in {"BOS", "CHoCH"}]
    swing_structure_events = [
        event for event in structure_events if event.structure_scope in {"swing", "external", "unknown"}
    ]
    sweep_events = [event for event in events if event.label == "Liquidity Sweep"]
    inferred = swing_structure_events[-1].direction if swing_structure_events else infer_trend(swings)
    normalized_bias = bias_hint.lower() if bias_hint and bias_hint.lower() in {"bullish", "bearish"} else None
    entry_low: float | None = None
    entry_high: float | None = None
    structural_invalidation: float | None = None
    execution_invalidation: float | None = None
    invalidation: float | None = None
    stop_buffer: float | None = None
    stop_buffer_atr: float | None = None
    stop_quality = "unknown"
    targets: list[float] = []
    warnings: list[str] = []
    conditions: list[str] = []
    selected_poi: Zone | None = None
    liquidity_target: float | None = None
    atr = _atr(df, lookback=config.atr_lookback)

    if normalized_bias and inferred in {"bullish", "bearish"} and inferred != normalized_bias:
        warnings.append(
            f"HTF bias hint is {normalized_bias}, but latest execution-timeframe swing structure is {inferred}; "
            "do not override HTF bias without a protected HTF break."
        )

    if direction not in {"bullish", "bearish"}:
        warnings.append("Directional bias is neutral. Wait for clearer higher-timeframe structure.")

    liquidity_levels = sorted(
        {
            round(zone.high if zone.direction == "bearish" else zone.low, 5)
            for zone in zones
            if zone.kind == "liquidity"
        }
    )

    allowed_poi_statuses = {"fresh"} if config.require_fresh_poi else {"fresh", "partial"}
    allowed_poi_kinds = set(config.allowed_poi_kinds or ["fvg", "order_block"])
    poi_candidates = [
        zone
        for zone in zones
        if zone.kind in allowed_poi_kinds
        and zone.direction == direction
        and zone.status in allowed_poi_statuses
        and (zone.end_index is None or len(df) - zone.end_index <= config.max_zone_age_bars)
        and ((zone.high - zone.low) / max(current_close, 1e-9) * 10000.0 >= config.min_poi_width_bps)
    ]

    def poi_rank(zone: Zone) -> float:
        center = (zone.low + zone.high) / 2.0
        distance_penalty = min(0.25, abs(center - current_close) / max(atr, 1e-9) * 0.035)
        location_bonus = 0.08 if (
            (direction == "bullish" and zone.high <= midpoint)
            or (direction == "bearish" and zone.low >= midpoint)
        ) else 0.0
        status_bonus = 0.06 if zone.status == "fresh" else 0.02 if zone.status == "partial" else 0.0
        if poi_selection == "nearest":
            return max(0.0, min(1.0, zone.score + status_bonus - distance_penalty * 1.4))
        if poi_selection == "best_location":
            return max(0.0, min(1.0, zone.score + location_bonus * 1.5 + status_bonus))
        return max(0.0, min(1.0, zone.score + location_bonus + status_bonus - distance_penalty))

    if direction == "bullish":
        future_or_near = [zone for zone in poi_candidates if zone.low <= current_close + atr * config.poi_proximity_atr]
        future_or_near.sort(key=poi_rank, reverse=True)
        selected_poi = future_or_near[0] if future_or_near else None
        if selected_poi:
            entry_low, entry_high = selected_poi.low, selected_poi.high
        target_floor = max(current_close, entry_high) if entry_high is not None else current_close
        targets = [price for price in liquidity_levels if price > target_floor][:2]
        fallback_target = round(range_high, 5)
        if not targets and fallback_target > target_floor:
            targets = [fallback_target]
        if not targets:
            warnings.append("No external bullish liquidity target lies beyond the proposed entry; no target issued.")
        liquidity_target = targets[0] if targets else None
        conditions = [
            "Wait for a sell-side liquidity sweep, bullish displacement, and 15m CHoCH/BOS before entry.",
            (
                "Prefer the selected bullish POI only while it remains fresh in discount."
                if config.require_fresh_poi
                else "Prefer the selected bullish POI only while it remains fresh or partially mitigated in discount."
            ),
        ]
    elif direction == "bearish":
        future_or_near = [zone for zone in poi_candidates if zone.high >= current_close - atr * config.poi_proximity_atr]
        future_or_near.sort(key=poi_rank, reverse=True)
        selected_poi = future_or_near[0] if future_or_near else None
        if selected_poi:
            entry_low, entry_high = selected_poi.low, selected_poi.high
        target_ceiling = min(current_close, entry_low) if entry_low is not None else current_close
        targets = [price for price in reversed(liquidity_levels) if price < target_ceiling][:2]
        fallback_target = round(range_low, 5)
        if not targets and fallback_target < target_ceiling:
            targets = [fallback_target]
        if not targets:
            warnings.append("No external bearish liquidity target lies beyond the proposed entry; no target issued.")
        liquidity_target = targets[0] if targets else None
        conditions = [
            "Wait for a buy-side liquidity sweep, bearish displacement, and 15m CHoCH/BOS before entry.",
            (
                "Prefer the selected bearish POI only while it remains fresh in premium."
                if config.require_fresh_poi
                else "Prefer the selected bearish POI only while it remains fresh or partially mitigated in premium."
            ),
        ]
    else:
        targets = []

    recent_sweep = next(
        (
            event
            for event in reversed(sweep_events)
            if event.direction == direction and len(df) - event.index <= config.confirmation_lookback
        ),
        None,
    )
    recent_break = next(
        (
            event
            for event in reversed(structure_events)
            if event.direction == direction and len(df) - event.index <= config.confirmation_lookback
        ),
        None,
    )
    has_sweep = recent_sweep is not None
    has_displacement_break = recent_break is not None and recent_break.displacement_score >= config.displacement_body_factor
    has_confirmation = bool(has_sweep and has_displacement_break and recent_sweep and recent_break and recent_sweep.index <= recent_break.index)
    has_poi = selected_poi is not None
    price_in_poi = bool(selected_poi and selected_poi.low <= current_close <= selected_poi.high)
    price_near_poi = bool(
        selected_poi
        and (
            price_in_poi
            or abs(current_close - ((selected_poi.low + selected_poi.high) / 2.0)) <= atr * config.poi_proximity_atr
        )
    )
    poi_location_ok = bool(
        selected_poi
        and (
            (direction == "bullish" and selected_poi.high <= midpoint)
            or (direction == "bearish" and selected_poi.low >= midpoint)
        )
    )

    structural_edge: float | None = None
    if selected_poi and direction == "bullish":
        structural_edge = min(selected_poi.low, recent_sweep.swept_level or selected_poi.low) if recent_sweep else selected_poi.low
        raw_stop = structural_edge * (1.0 - config.structural_stop_margin_bps / 10000.0)
        volatility_stop = structural_edge - atr * config.stop_buffer_atr_mult
        structural_invalidation = round(raw_stop, 5)
        execution_invalidation = round(min(raw_stop, volatility_stop), 5)
    elif selected_poi and direction == "bearish":
        structural_edge = max(selected_poi.high, recent_sweep.swept_level or selected_poi.high) if recent_sweep else selected_poi.high
        raw_stop = structural_edge * (1.0 + config.structural_stop_margin_bps / 10000.0)
        volatility_stop = structural_edge + atr * config.stop_buffer_atr_mult
        structural_invalidation = round(raw_stop, 5)
        execution_invalidation = round(max(raw_stop, volatility_stop), 5)

    invalidation = execution_invalidation
    if structural_edge is not None and execution_invalidation is not None:
        stop_buffer = round(abs(execution_invalidation - structural_edge), 5)
        stop_buffer_atr = round(stop_buffer / max(atr, 1e-9), 2)
        adjusted = structural_invalidation is not None and abs(execution_invalidation - structural_invalidation) > 1e-9
        stop_quality = "volatility_adjusted" if adjusted else "structural_ok"
        if config.stop_buffer_atr_mult > 0 and stop_buffer_atr + 1e-9 < config.stop_buffer_atr_mult:
            stop_quality = "too_tight"
        if adjusted:
            warnings.append(
                "Execution stop widened from raw structural invalidation "
                f"{structural_invalidation:.5f} to {execution_invalidation:.5f} "
                f"to require at least {config.stop_buffer_atr_mult:.2f} ATR beyond the POI/sweep edge."
            )
    has_stop_buffer = bool(invalidation is not None and stop_quality in {"structural_ok", "volatility_adjusted"})

    risk_reward: float | None = None
    if entry_low is not None and entry_high is not None and invalidation is not None and targets:
        entry = (entry_low + entry_high) / 2.0
        if direction == "bullish":
            risk = max(entry - invalidation, 1e-9)
            reward = max(targets[0] - entry, 0.0)
        elif direction == "bearish":
            risk = max(invalidation - entry, 1e-9)
            reward = max(entry - targets[0], 0.0)
        else:
            risk, reward = 0.0, 0.0
        risk_reward = round(reward / risk, 2) if risk > 0 else None
    has_rr = bool(risk_reward is not None and risk_reward >= config.risk_reward_floor)

    location = "discount" if current_close < midpoint else "premium"
    checklist = {
        "directional_bias": direction in {"bullish", "bearish"},
        "fresh_or_partial_poi": has_poi,
        "premium_discount_aligned": poi_location_ok,
        "liquidity_sweep": has_sweep,
        "displacement_break": has_displacement_break,
        "sweep_before_break": has_confirmation,
        "price_at_or_near_poi": price_near_poi,
        "stop_has_volatility_buffer": has_stop_buffer,
        "risk_reward_floor": has_rr,
    }
    confluence_score = round(sum(1 for value in checklist.values() if value) / len(checklist), 2)

    if not has_poi:
        poi_wording = "fresh" if config.require_fresh_poi else "fresh/partial"
        warnings.append(f"No {poi_wording} POI survived the quality and age filters.")
    if not has_sweep:
        warnings.append("No recent liquidity sweep in the intended direction.")
    if not has_displacement_break:
        warnings.append("No recent displacement-backed BOS/CHoCH in the intended direction.")
    if has_sweep and has_displacement_break and not has_confirmation:
        warnings.append("Sweep and structure break are out of sequence; wait for a clean sweep-then-break model.")
    if selected_poi and not poi_location_ok:
        warnings.append("Selected POI is not cleanly aligned with premium/discount rules.")
    if selected_poi and not price_near_poi:
        warnings.append("Price is not at or near the selected POI; treat this as a watchlist scenario.")
    if selected_poi and not has_stop_buffer:
        warnings.append("No execution-grade stop could be built from the selected POI and volatility context.")
    if risk_reward is not None and risk_reward < config.risk_reward_floor:
        warnings.append(f"Projected risk/reward is below the configured floor of {config.risk_reward_floor:.1f}.")

    setup_grade = "C"
    verdict = "Pass"
    entry_type = "no_trade"
    risk_pct = 0.0

    full_pass = all(
        [
            checklist["directional_bias"],
            checklist["fresh_or_partial_poi"],
            checklist["premium_discount_aligned"],
            checklist["liquidity_sweep"],
            checklist["displacement_break"],
            checklist["sweep_before_break"],
            checklist["price_at_or_near_poi"],
            checklist["stop_has_volatility_buffer"],
            checklist["risk_reward_floor"],
        ]
    )

    retrace_ready = all(
        [
            checklist["directional_bias"],
            checklist["fresh_or_partial_poi"],
            checklist["premium_discount_aligned"],
            checklist["liquidity_sweep"],
            checklist["displacement_break"],
            checklist["sweep_before_break"],
            checklist["stop_has_volatility_buffer"],
            checklist["risk_reward_floor"],
        ]
    ) and not checklist["price_at_or_near_poi"]

    if full_pass:
        strong_poi = selected_poi is not None and selected_poi.score >= 0.82
        strong_break = recent_break is not None and recent_break.strength == "strong"
        setup_grade = "A+" if strong_poi and strong_break else "A"
        verdict = "Execute"
        entry_type = "aggressive_limit" if setup_grade == "A+" and price_in_poi else "confirmation"
        risk_pct = 2.0 if setup_grade == "A+" else 1.0
    elif retrace_ready:
        setup_grade = "B"
        verdict = "Watch Retrace"
        entry_type = "confirmation"
    elif has_poi and (has_sweep or has_displacement_break):
        setup_grade = "B"
        verdict = "Watch"
        entry_type = "confirmation" if has_sweep else "no_trade"

    # HARD GATE: R:R floor is a binary veto. It cannot be overridden by partial
    # confluence, confidence, or any downstream layer.
    if not has_rr:
        verdict = "Pass"
        setup_grade = "C"
        entry_type = "no_trade"
        risk_pct = 0.0

    # A higher-timeframe POI is a route map, not a limit order. It can only
    # surface a watch state while the 15m model is otherwise a pass; it never
    # changes the execution checklist or manufactures entry/SL/TP levels.
    # Only promote to Watch HTF POI if the HTF POI direction matches this plan.
    if verdict == "Pass" and htf_poi and htf_poi.zone.direction == direction and htf_poi.state in {"approaching", "at_poi"}:
        verdict = "Watch HTF POI"
        setup_grade = "C"
        targets = []
        liquidity_target = None
        risk_reward = None
        conditions.insert(
            0,
            (
                f"Monitor the {htf_poi.timeframe} {htf_poi.zone.label} "
                f"{htf_poi.zone.low:.5f}-{htf_poi.zone.high:.5f} ({htf_poi.state}); "
                "do not enter until a 15m sweep, displacement, and internal structure break form at the zone."
            ),
        )
        warnings.append(
            "Higher-timeframe POI watch only: no executable entry, stop, target, or risk has been issued."
        )

    confidence = min(0.9, 0.18 + confluence_score * 0.62 + (selected_poi.score * 0.15 if selected_poi else 0.0))
    poi_text = f"{selected_poi.label} {selected_poi.low:.5f}-{selected_poi.high:.5f}" if selected_poi else "no valid 15m POI"
    htf_poi_text = (
        f" {htf_poi.timeframe} watch zone: {htf_poi.zone.label} {htf_poi.zone.low:.5f}-{htf_poi.zone.high:.5f} "
        f"({htf_poi.state}, {htf_poi.distance_atr:.2f} ATR away)."
        if htf_poi
        else ""
    )

    thesis = (
        f"Current structure reads {direction}. Price is trading in {location} of the recent dealing range "
        f"between {range_low:.4f} and {range_high:.4f}. Selected POI: {poi_text}. "
        f"Confluence score is {confluence_score:.2f}; verdict is {verdict} with setup grade {setup_grade}."
        f"{htf_poi_text}"
    )
    if invalidation is not None and structural_invalidation is not None:
        conditions.append(
            "Use execution invalidation for the SL; raw structural invalidation is kept only as the thesis-failure marker."
        )

    return TradePlan(
        direction=direction,
        entry_type=entry_type,  # type: ignore[arg-type]
        setup_grade=setup_grade,  # type: ignore[arg-type]
        verdict=verdict,  # type: ignore[arg-type]
        risk_pct=risk_pct,
        entry_low=entry_low,
        entry_high=entry_high,
        structural_invalidation=structural_invalidation,
        execution_invalidation=execution_invalidation,
        invalidation=invalidation,
        stop_buffer=stop_buffer,
        stop_buffer_atr=stop_buffer_atr,
        stop_quality=stop_quality,
        targets=[round(target, 5) for target in targets],
        risk_reward=risk_reward,
        confidence=round(confidence, 2),
        confluence_score=confluence_score,
        liquidity_target=liquidity_target,
        selected_poi=selected_poi,
        selected_htf_poi=htf_poi,
        checklist=checklist,
        thesis=thesis,
        conditions=conditions,
        warnings=warnings,
    )


def build_trade_plan(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    zones: list[Zone],
    events: list[StructureEvent],
    config: RuleConfig,
    bias_hint: str | None = None,
    poi_selection: str = "balanced",
    htf_poi: HigherTimeframePoi | None = None,
) -> TradePlan:
    """Backward-compatible single-direction plan builder.

    Resolves one direction from bias_hint or inferred trend and delegates to
    the direction-agnostic helper.
    """
    structure_events = [event for event in events if event.label in {"BOS", "CHoCH"}]
    swing_structure_events = [
        event for event in structure_events if event.structure_scope in {"swing", "external", "unknown"}
    ]
    inferred = swing_structure_events[-1].direction if swing_structure_events else infer_trend(swings)
    normalized_bias = bias_hint.lower() if bias_hint and bias_hint.lower() in {"bullish", "bearish"} else None
    direction = normalized_bias or inferred
    return _build_trade_plan_for_direction(
        df=df,
        swings=swings,
        zones=zones,
        events=events,
        config=config,
        direction=direction,
        bias_hint=bias_hint,
        poi_selection=poi_selection,
        htf_poi=htf_poi,
    )


def build_dual_trade_plan(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    zones: list[Zone],
    events: list[StructureEvent],
    config: RuleConfig,
    bias_hint: str | None = None,
    poi_selection: str = "balanced",
    htf_poi: HigherTimeframePoi | None = None,
) -> dict[str, TradePlan]:
    """Build both bullish and bearish trade plans from the same precomputed structure.

    Each plan uses engine-owned POI, stop, target, and R:R. The bullish plan
    ignores bearish POIs and vice versa. This is the keystone of the Fusion
    Engine: fusion scores two competing hypotheses rather than overriding a
    single baseline.
    """
    plans: dict[str, TradePlan] = {}
    for direction in ("bullish", "bearish"):
        plans[direction] = _build_trade_plan_for_direction(
            df=df,
            swings=swings,
            zones=zones,
            events=events,
            config=config,
            direction=direction,
            bias_hint=bias_hint,
            poi_selection=poi_selection,
            htf_poi=htf_poi,
        )
    return plans



def analyze_ohlcv(
    ohlcv_path: str,
    symbol: str,
    timeframe: str,
    config: RuleConfig,
    bias_hint: str | None = None,
    notes: str | None = None,
    input_type: str = "ohlcv",
) -> tuple[AnalysisResult, pd.DataFrame]:
    df = load_ohlcv_csv(ohlcv_path)
    return analyze_dataframe(
        df=df,
        symbol=symbol,
        timeframe=timeframe,
        config=config,
        bias_hint=bias_hint,
        notes=notes,
        input_type=input_type,
    )


def analyze_dataframe(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    config: RuleConfig,
    bias_hint: str | None = None,
    notes: str | None = None,
    input_type: str = "ohlcv",
    poi_selection: str = "balanced",
    htf_poi: HigherTimeframePoi | None = None,
) -> tuple[AnalysisResult, pd.DataFrame]:
    df = df.copy()
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = (
        df.sort_values("timestamp")
        .dropna(subset=["timestamp", "open", "high", "low", "close"])
        .tail(config.lookback_bars)
        .reset_index(drop=True)
    )
    swings = detect_swings(df, config, pivot_window=_scope_pivot_window(config, "swing"))
    internal_swings = detect_swings(df, config, pivot_window=_scope_pivot_window(config, "internal"))
    equal_levels = detect_equal_levels(swings, config)
    fvgs = detect_fvgs(df, config)
    swing_structure_events = detect_structure_events(df, swings, config, structure_scope="swing")
    internal_structure_events = detect_structure_events(df, internal_swings, config, structure_scope="internal")
    structure_events = _merge_structure_events(swing_structure_events, internal_structure_events)
    sweep_events = detect_liquidity_sweeps(df, swings, config)
    events = sorted(structure_events + sweep_events, key=lambda event: event.index)[-18:]
    order_blocks = detect_order_blocks(df, swing_structure_events, config)
    all_zones = equal_levels + fvgs + order_blocks
    dual_plans = build_dual_trade_plan(
        df,
        swings,
        all_zones,
        events,
        config,
        bias_hint=bias_hint,
        poi_selection=poi_selection,
        htf_poi=htf_poi,
    )
    # Primary plan remains the single-direction view for backward compatibility.
    # If a bias_hint is supplied, prefer that direction; otherwise use the
    # direction with the higher confluence score, falling back to inferred trend.
    primary_direction = bias_hint.lower() if bias_hint and bias_hint.lower() in {"bullish", "bearish"} else None
    if primary_direction is None:
        primary_direction = dual_plans["bullish"].direction
        if dual_plans["bearish"].confluence_score > dual_plans["bullish"].confluence_score:
            primary_direction = dual_plans["bearish"].direction
    trade_plan = dual_plans[primary_direction]
    session_context = summarize_session_context(df)
    range_low, range_high = _select_range(df, swings)
    metrics = {
        "bars_analyzed": int(len(df)),
        "latest_close": float(df["close"].iloc[-1]),
        "range_low": round(range_low, 5),
        "range_high": round(range_high, 5),
        "swing_count": int(len(swings)),
        "zone_count": int(len(all_zones)),
        "event_count": int(len(events)),
        "inferred_trend": trade_plan.direction,
    }
    limitations = [
        "The rule engine is heuristic and should be replaced or tightened with your house rules.",
        "Order blocks and structure shifts are detected from candles, not from semantic chart context.",
        "Screenshot-only inference is not performed unless OHLCV or manual notes are also supplied.",
        "This output is analysis support, not financial advice or execution logic.",
    ]
    result = AnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        input_type=input_type,  # type: ignore[arg-type]
        generated_at=datetime.now(timezone.utc).isoformat(),
        bias_hint=bias_hint,
        notes=notes,
        metrics=metrics,
        session_context=session_context,
        swings=swings,
        zones=all_zones,
        events=events,
        trade_plan=trade_plan,
        bullish_plan=dual_plans["bullish"],
        bearish_plan=dual_plans["bearish"],
        limitations=limitations,
    )
    return result, df


def build_trade_plan_markdown(result: AnalysisResult) -> str:
    lines = [
        f"# {result.symbol} {result.timeframe} Trade Plan",
        "",
        f"Generated: {result.generated_at}",
        f"Input type: {result.input_type}",
        "",
        "## Verdict",
        f"{result.trade_plan.verdict} / Grade {result.trade_plan.setup_grade}",
        f"Entry type: {result.trade_plan.entry_type}",
        f"Risk allowed: {result.trade_plan.risk_pct:.1f}%",
        f"Confluence score: {result.trade_plan.confluence_score:.2f}",
        "",
        "## Thesis",
        result.trade_plan.thesis,
        "",
        "## Direction",
        result.trade_plan.direction,
        "",
        "## Key Levels",
        f"- Entry zone: {format_zone(result.trade_plan.entry_low, result.trade_plan.entry_high)}",
        (
            "- HTF POI: "
            f"{result.trade_plan.selected_htf_poi.timeframe} "
            f"{result.trade_plan.selected_htf_poi.zone.label} "
            f"{format_zone(result.trade_plan.selected_htf_poi.zone.low, result.trade_plan.selected_htf_poi.zone.high)} "
            f"({result.trade_plan.selected_htf_poi.state}, "
            f"{result.trade_plan.selected_htf_poi.distance_atr:.2f} ATR away)"
            if result.trade_plan.selected_htf_poi
            else "- HTF POI: None"
        ),
        f"- Execution SL / invalidation: {format_level(result.trade_plan.invalidation)}",
        f"- Structural invalidation: {format_level(result.trade_plan.structural_invalidation)}",
        (
            f"- Stop buffer: {result.trade_plan.stop_buffer_atr:.2f} ATR ({result.trade_plan.stop_quality})"
            if result.trade_plan.stop_buffer_atr is not None
            else f"- Stop buffer: {result.trade_plan.stop_quality}"
        ),
        f"- Liquidity target: {format_level(result.trade_plan.liquidity_target)}",
        f"- Targets: {', '.join(format_level(target) for target in result.trade_plan.targets) or 'None'}",
        f"- Risk/Reward: {result.trade_plan.risk_reward if result.trade_plan.risk_reward is not None else 'N/A'}",
        "",
        "## Confluence Checklist",
    ]
    if result.trade_plan.checklist:
        lines.extend(f"- [{'x' if value else ' '}] {key.replace('_', ' ')}" for key, value in result.trade_plan.checklist.items())
    else:
        lines.append("- No checklist was generated.")
    lines.extend([
        "",
        "## Conditions",
    ])
    if result.trade_plan.conditions:
        lines.extend(f"- {condition}" for condition in result.trade_plan.conditions)
    else:
        lines.append("- Wait for clearer structure.")
    lines.extend(["", "## Warnings"])
    if result.trade_plan.warnings:
        lines.extend(f"- {warning}" for warning in result.trade_plan.warnings)
    else:
        lines.append("- None.")
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in result.limitations)

    # Dual-direction assessment (new). Only shown when both plans are populated
    # and at least one is non-Pass, so the output surfaces competing theses.
    bullish = result.bullish_plan
    bearish = result.bearish_plan
    if bullish and bearish:
        both_pass = bullish.verdict == "Pass" and bearish.verdict == "Pass"
        one_non_pass = bullish.verdict != "Pass" or bearish.verdict != "Pass"
        if one_non_pass or not both_pass:
            lines.extend([
                "",
                "## Dual-Direction Assessment",
                f"| | Bullish | Bearish |",
                f"| verdict | {bullish.verdict} / {bullish.setup_grade} | {bearish.verdict} / {bearish.setup_grade} |",
                f"| confluence | {bullish.confluence_score:.2f} | {bearish.confluence_score:.2f} |",
                f"| R:R | {bullish.risk_reward if bullish.risk_reward is not None else 'N/A'} | {bearish.risk_reward if bearish.risk_reward is not None else 'N/A'} |",
                f"| entry | {format_zone(bullish.entry_low, bullish.entry_high)} | {format_zone(bearish.entry_low, bearish.entry_high)} |",
                f"| stop | {format_level(bullish.invalidation)} | {format_level(bearish.invalidation)} |",
                f"| target | {format_level(bullish.liquidity_target)} | {format_level(bearish.liquidity_target)} |",
            ])
            if bullish.verdict == "Pass" and bearish.verdict == "Pass":
                lines.append("Neither direction has a valid executable setup.")
            elif bullish.verdict != "Pass" and bearish.verdict != "Pass":
                lines.append("Both directions have candidate setups; the primary plan above is the higher-confluence side.")

    return "\n".join(lines) + "\n"


def format_level(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.5f}"


def format_zone(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "N/A"
    return f"{low:.5f} - {high:.5f}"
