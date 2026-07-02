"""Decision-grade active range authority for AI SMC analysis.

This module answers a narrower question than the raw perception layer:
which protected swing leg is the AI allowed to reason from right now?

It deliberately rejects dataset-wide OHLCV highs/lows. A trader-grade active
range must come from confirmed, recent swing structure and must be narrow
enough to be usable for the current decision context.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd


TIMEFRAME_PRIORITY = ("4h", "1h", "15m", "1d")
PIVOT_WINDOWS = {"15m": 5, "1h": 4, "4h": 3, "1d": 2}
MAX_WIDTH_ATR = {"15m": 28.0, "1h": 24.0, "4h": 22.0, "1d": 20.0}
MIN_WIDTH_ATR = 1.0


@dataclass(frozen=True)
class SwingPivot:
    pivot_id: str
    timeframe: str
    index: int
    timestamp: str
    kind: str
    price: float
    prominence_atr: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pivot_id": self.pivot_id,
            "timeframe": self.timeframe,
            "index": self.index,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "price": self.price,
            "prominence_atr": round(self.prominence_atr, 4),
        }


def resolve_active_range_authority(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    preferred_timeframes: Sequence[str] = TIMEFRAME_PRIORITY,
    current_price: float | None = None,
) -> dict[str, Any]:
    """Resolve the active dealing range from recent swing structure.

    The selected range is the most recent alternating swing-high/swing-low pair
    that brackets current price and passes width sanity checks. If no such pair
    exists, the caller gets an explicit unresolved report rather than a broad
    high/low fallback.
    """
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    decision_price = current_price if current_price is not None else _latest_execution_price(timeframe_dfs)

    for timeframe in preferred_timeframes:
        df = timeframe_dfs.get(timeframe)
        if df is None or df.empty:
            continue
        candidate = _candidate_for_timeframe(
            symbol=symbol,
            timeframe=timeframe,
            df=_normalize_df(df),
            current_price=decision_price,
        )
        if candidate["status"] == "RESOLVED_ACTIVE_RANGE":
            candidates.append(candidate)
        else:
            rejected.append(candidate)

    selected = candidates[0] if candidates else None
    return {
        "schema": "active_range_authority_v1",
        "symbol": symbol,
        "status": "RESOLVED_ACTIVE_RANGE" if selected else "RANGE_UNRESOLVED_REVIEW_REQUIRED",
        "method": "recent_alternating_protected_swing_pair_not_ohlcv_summary",
        "selected_range": selected,
        "candidate_ranges": candidates,
        "rejected_ranges": rejected,
        "forbidden_sources": ["ohlcv_summary_high_low", "dataset_high_low", "visible_window_extremes_without_structure"],
        "review_rule": (
            "If no recent swing pair passes width and bracketing checks, the AI must return REVIEW_REQUIRED "
            "or WATCH_ONLY without inventing levels."
        ),
    }


def _candidate_for_timeframe(
    *,
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    current_price: float | None = None,
) -> dict[str, Any]:
    window = PIVOT_WINDOWS.get(timeframe, 4)
    tail = df.tail(_tail_size(timeframe)).reset_index(drop=True)
    current_price = float(current_price) if current_price is not None else float(tail["close"].iloc[-1])
    atr = _atr(tail)
    pivots = _detect_pivots(symbol=symbol, timeframe=timeframe, df=tail, window=window, atr=atr)
    pair = _latest_bracketing_pair(pivots, current_price=current_price)
    base = {
        "symbol": symbol,
        "timeframe": timeframe,
        "current_price": current_price,
        "atr": round(atr, 8),
        "pivot_window": window,
        "pivot_count": len(pivots),
        "source": "protected_swing_pair",
        "not_source": "ohlcv_summary_high_low",
    }
    if pair is None:
        return {
            **base,
            "status": "REJECTED_NO_BRACKETING_SWING_PAIR",
            "reason": "No recent alternating swing high/low pair brackets current price.",
            "recent_pivots": [pivot.to_dict() for pivot in pivots[-8:]],
        }

    first, second = pair
    high_pivot = first if first.kind == "high" else second
    low_pivot = first if first.kind == "low" else second
    high = float(high_pivot.price)
    low = float(low_pivot.price)
    width = high - low
    width_atr = width / max(atr, 1e-9)
    max_width = MAX_WIDTH_ATR.get(timeframe, 24.0)
    if width_atr < MIN_WIDTH_ATR:
        return {
            **base,
            "status": "REJECTED_RANGE_TOO_NARROW",
            "reason": f"Swing range width {width_atr:.2f} ATR is below minimum {MIN_WIDTH_ATR:.2f}.",
            "range_high": high,
            "range_low": low,
            "width_atr": round(width_atr, 4),
            "source_pivots": [first.to_dict(), second.to_dict()],
        }
    if width_atr > max_width:
        return {
            **base,
            "status": "REJECTED_RANGE_TOO_WIDE",
            "reason": f"Swing range width {width_atr:.2f} ATR exceeds {timeframe} maximum {max_width:.2f}.",
            "range_high": high,
            "range_low": low,
            "width_atr": round(width_atr, 4),
            "source_pivots": [first.to_dict(), second.to_dict()],
        }

    direction = "bearish" if high_pivot.index < low_pivot.index else "bullish"
    equilibrium = (high + low) / 2.0
    price_location = "premium" if current_price > equilibrium else "discount" if current_price < equilibrium else "equilibrium"
    return {
        **base,
        "status": "RESOLVED_ACTIVE_RANGE",
        "range_id": f"{symbol}:{timeframe}:active_range:{high_pivot.pivot_id}:{low_pivot.pivot_id}",
        "direction": direction,
        "range_high": high,
        "range_low": low,
        "equilibrium": equilibrium,
        "price_location": price_location,
        "width": width,
        "width_atr": round(width_atr, 4),
        "max_width_atr": max_width,
        "protected_high": high,
        "protected_low": low,
        "protected_high_pivot_id": high_pivot.pivot_id,
        "protected_low_pivot_id": low_pivot.pivot_id,
        "source_pivots": [first.to_dict(), second.to_dict()],
        "external_liquidity": [
            {"side": "buy_side", "price": high, "source_pivot_id": high_pivot.pivot_id},
            {"side": "sell_side", "price": low, "source_pivot_id": low_pivot.pivot_id},
        ],
        "authority_notes": [
            "Active range selected from recent alternating swing structure.",
            "Broad candle extremes were excluded from range selection.",
        ],
    }


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={"index": "timestamp"})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out.sort_values("timestamp").reset_index(drop=True)


def _latest_execution_price(timeframe_dfs: Mapping[str, pd.DataFrame]) -> float | None:
    for timeframe in ("15m", "5m", "1h", "4h", "1d"):
        df = timeframe_dfs.get(timeframe)
        if df is not None and not df.empty:
            return float(_normalize_df(df)["close"].iloc[-1])
    return None


def _tail_size(timeframe: str) -> int:
    return {"15m": 320, "1h": 240, "4h": 180, "1d": 160}.get(timeframe, 240)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = float(true_range.tail(period).mean())
    if value <= 0:
        value = float((high - low).tail(period).mean())
    return max(value, 1e-9)


def _detect_pivots(*, symbol: str, timeframe: str, df: pd.DataFrame, window: int, atr: float) -> list[SwingPivot]:
    pivots: list[SwingPivot] = []
    high = df["high"].astype(float).to_list()
    low = df["low"].astype(float).to_list()
    timestamps = df["timestamp"].to_list()
    for idx in range(window, len(df) - window):
        high_slice = high[idx - window : idx + window + 1]
        low_slice = low[idx - window : idx + window + 1]
        price_high = high[idx]
        price_low = low[idx]
        if price_high == max(high_slice) and high_slice.count(price_high) == 1:
            prominence = (price_high - min(low_slice)) / max(atr, 1e-9)
            if prominence >= 0.55:
                pivots.append(
                    SwingPivot(
                        pivot_id=f"{symbol}:{timeframe}:swing_high:{idx}:{pd.Timestamp(timestamps[idx]).isoformat()}",
                        timeframe=timeframe,
                        index=idx,
                        timestamp=pd.Timestamp(timestamps[idx]).isoformat(),
                        kind="high",
                        price=price_high,
                        prominence_atr=prominence,
                    )
                )
        if price_low == min(low_slice) and low_slice.count(price_low) == 1:
            prominence = (max(high_slice) - price_low) / max(atr, 1e-9)
            if prominence >= 0.55:
                pivots.append(
                    SwingPivot(
                        pivot_id=f"{symbol}:{timeframe}:swing_low:{idx}:{pd.Timestamp(timestamps[idx]).isoformat()}",
                        timeframe=timeframe,
                        index=idx,
                        timestamp=pd.Timestamp(timestamps[idx]).isoformat(),
                        kind="low",
                        price=price_low,
                        prominence_atr=prominence,
                    )
                )
    pivots.sort(key=lambda pivot: pivot.index)
    return _dedupe_adjacent_same_kind(pivots)


def _dedupe_adjacent_same_kind(pivots: list[SwingPivot]) -> list[SwingPivot]:
    if not pivots:
        return []
    out: list[SwingPivot] = []
    for pivot in pivots:
        if not out or out[-1].kind != pivot.kind:
            out.append(pivot)
            continue
        previous = out[-1]
        if pivot.kind == "high" and pivot.price > previous.price:
            out[-1] = pivot
        elif pivot.kind == "low" and pivot.price < previous.price:
            out[-1] = pivot
    return out


def _latest_bracketing_pair(pivots: list[SwingPivot], *, current_price: float) -> tuple[SwingPivot, SwingPivot] | None:
    for idx in range(len(pivots) - 2, -1, -1):
        first = pivots[idx]
        second = pivots[idx + 1]
        if first.kind == second.kind:
            continue
        high = max(first.price, second.price)
        low = min(first.price, second.price)
        if low <= current_price <= high:
            return first, second
    return None
