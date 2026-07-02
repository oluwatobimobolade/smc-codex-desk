"""Bridge between PerceptionEngineV2 and the legacy fusion pipeline.

The V2 engine operates on Pydantic Candle objects with Decimal precision.
The legacy fusion pipeline operates on pd.DataFrame with float precision.

This bridge:
1. Converts pd.DataFrame rows to Candle objects (with Decimal prices).
2. Runs PerceptionEngineV2 on the converted candles.
3. Returns a simplified summary for the fusion observability output.

The V2 engine runs in SHADOW MODE: its output is logged for review but
does not influence the deterministic engine verdict. It exists to validate
that the legacy engine's structure detection matches the V2 engine's
object-based detection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import pandas as pd

from smc_desk.data.schemas import Candle
from smc_desk.perception.engine_v2 import PerceptionEngineV2, PerceptionSnapshot
from smc_desk.perception.ontology import Direction


def dataframe_to_candles(
    df: pd.DataFrame,
    venue: str = "BINANCE",
    instrument: str = "UNKNOWN",
    timeframe: str = "15m",
) -> list[Candle]:
    """Convert a pd.DataFrame to a list of Pydantic Candle objects."""
    candles: list[Candle] = []
    for idx, row in df.iterrows():
        ts = row["timestamp"]
        if isinstance(ts, pd.Timestamp):
            dt = ts.to_pydatetime()
        else:
            dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        interval = pd.Timedelta(minutes=15) if timeframe == "15m" else pd.Timedelta(minutes=1)
        open_time = dt
        close_time = open_time + interval

        candles.append(Candle(
            venue=venue,
            instrument=instrument,
            timeframe=timeframe,
            open_time=open_time,
            close_time=close_time,
            open=Decimal(str(float(row["open"]))),
            high=Decimal(str(float(row["high"]))),
            low=Decimal(str(float(row["low"]))),
            close=Decimal(str(float(row["close"]))),
            volume=Decimal(str(float(row.get("volume", 0.0)))),
            trade_count=int(row.get("trade_count", 100)),
            is_complete=True,
            is_closed=True,
            contains_gap=False,
        ))
    return candles


def run_v2_perception_shadow(
    df: pd.DataFrame,
    venue: str = "BINANCE",
    instrument: str = "UNKNOWN",
    timeframe: str = "15m",
) -> dict[str, Any]:
    """Run PerceptionEngineV2 in shadow mode and return a summary.

    Returns a dict suitable for inclusion in the fusion observability
    output. The V2 output is purely informational; the fusion verdict
    is still determined by the legacy engine + intent + features.
    """
    try:
        candles = dataframe_to_candles(df, venue=venue, instrument=instrument, timeframe=timeframe)
        engine = PerceptionEngineV2()
        # Use the close time of the last candle as the decision time.
        decision_time = candles[-1].close_time
        snapshot = engine.analyze(candles, decision_time)

        return _summarize_snapshot(snapshot)
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "swings": [],
            "structure_breaks": [],
            "fvgs": [],
        }


def _summarize_snapshot(snapshot: PerceptionSnapshot) -> dict[str, Any]:
    """Convert a PerceptionSnapshot into a fusion-friendly summary."""
    swings: list[dict[str, Any]] = []
    for scale, scale_swings in snapshot.swings.items():
        for swing in scale_swings:
            swings.append({
                "scale": scale,
                "direction": swing.direction.value if hasattr(swing.direction, "value") else str(swing.direction),
                "price_high": float(swing.price_high) if swing.price_high else None,
                "price_low": float(swing.price_low) if swing.price_low else None,
                "pivot_time": swing.pivot_time.isoformat() if swing.pivot_time else None,
                "confidence": swing.confidence,
            })

    structure_breaks: list[dict[str, Any]] = []
    for brk in snapshot.structure_breaks:
        # StructureBreakObject has break_type (str) and evidence with broken_price
        brk_type = brk.break_type if isinstance(brk.break_type, str) else (
            brk.break_type.value if hasattr(brk.break_type, "value") else str(brk.break_type)
        )
        brk_direction = brk.direction
        if hasattr(brk_direction, "value"):
            brk_direction = brk_direction.value
        else:
            brk_direction = str(brk_direction)
        # Get price from evidence if available
        brk_price = None
        if hasattr(brk, "evidence") and hasattr(brk.evidence, "broken_price"):
            brk_price = float(brk.evidence.broken_price)
        structure_breaks.append({
            "type": brk_type,
            "direction": brk_direction,
            "price": brk_price,
            "scope": brk.structure_scope.value if hasattr(brk, "structure_scope") and hasattr(brk.structure_scope, "value") else "unknown",
        })

    fvgs: list[dict[str, Any]] = []
    for fvg in snapshot.fvgs:
        fvgs.append({
            "direction": fvg.direction.value if hasattr(fvg.direction, "value") else str(fvg.direction),
            "price_high": float(fvg.price_high) if fvg.price_high else None,
            "price_low": float(fvg.price_low) if fvg.price_low else None,
            "mitigated": fvg.mitigated if hasattr(fvg, "mitigated") else False,
        })

    state = snapshot.structure_state or {}

    return {
        "status": "ok",
        "decision_time": snapshot.decision_time.isoformat(),
        "swing_count": len(swings),
        "break_count": len(structure_breaks),
        "fvg_count": len(fvgs),
        "liquidity_level_count": len(getattr(snapshot, "liquidity_levels", []) or []),
        "sweep_count": len(getattr(snapshot, "sweeps", []) or []),
        "order_block_count": len(getattr(snapshot, "order_blocks", []) or []),
        "inducement_count": len(getattr(snapshot, "inducements", []) or []),
        "poi_grade_fvg_count": len(getattr(snapshot, "poi_grade_fvgs", []) or []),
        "current_direction": state.get("current_direction"),
        "swings": swings,
        "structure_breaks": structure_breaks,
        "fvgs": fvgs,
    }
