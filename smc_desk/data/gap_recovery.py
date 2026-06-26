"""Gap recovery: reconnect/disconnect handling for live candle streams.

When the WebSocket disconnects, candles may be missed. On reconnect:

1. Retrieve Binance server time.
2. Inspect the final persisted candle.
3. REST-fetch every interval since that candle.
4. Fill missing completed candles.
5. Verify continuity (no gaps remain).
6. Rebuild affected higher timeframes.
7. Report recovery status.

Do not simply reconnect from "now" — that loses market history and corrupts
the state machine.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from smc_desk.data.closed_candle_store import (
    CandleIdentity,
    ClosedCandle,
    ClosedCandleStore,
)


class GapStatus:
    """Status of gap detection after disconnection."""

    def __init__(self):
        self.gaps_detected: bool = False
        self.gap_count: int = 0
        self.missing_intervals: List[datetime] = []
        self.filled_count: int = 0
        self.continuity_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "gaps_detected": self.gaps_detected,
            "gap_count": self.gap_count,
            "missing_intervals": [t.isoformat() for t in self.missing_intervals],
            "filled_count": self.filled_count,
            "continuity_verified": self.continuity_verified,
        }


def compute_missing_intervals(
    store: ClosedCandleStore,
    server_time: datetime,
    interval_minutes: int = 15,
    max_lookback: int = 500,
) -> List[datetime]:
    """Compute which candle open times are missing between the last persisted
    candle and the current server time.

    Args:
        store: The closed candle store.
        server_time: Binance server time (UTC).
        interval_minutes: Candle interval in minutes (default 15).
        max_lookback: Maximum intervals to look back (prevents runaway).

    Returns:
        List of datetime open_times for missing candle intervals.
    """
    latest = store.latest_open_time()
    if latest is None:
        return []

    # Current expected open time (the forming candle's open)
    interval = timedelta(minutes=interval_minutes)
    current_bucket = server_time.replace(second=0, microsecond=0)
    # Align to interval boundary
    minutes_offset = current_bucket.minute % interval_minutes
    if minutes_offset > 0:
        current_bucket -= timedelta(minutes=minutes_offset)

    # The forming bucket is not yet closed. We need intervals up to the
    # last fully closed candle (current bucket - 1 interval for the
    # forming one, BUT we want closed candles, so we check up to one
    # interval BEFORE the current bucket).
    # Actually, the latest closed candle should have close_time <= server_time.
    # We check intervals from latest + 1 up to current_bucket.
    expected = latest + interval
    missing: List[datetime] = []
    count = 0

    while expected < current_bucket and count < max_lookback:
        # Skip the current forming bucket
        if expected >= current_bucket:
            break
        identity = CandleIdentity(
            venue="BINANCE", market_type="perpetual",
            symbol="BTCUSDT", timeframe="15m",
            open_time=expected,
        )
        if not store.has(identity):
            missing.append(expected)
            count += 1
        expected += interval
        count += 1

    return missing


def verify_continuity(
    store: ClosedCandleStore,
    interval_minutes: int = 15,
) -> bool:
    """Verify that all persisted candles form a continuous, gap-free sequence.

    Returns True if every candle's open_time equals the previous candle's
    close_time (expected next open).
    """
    candles = store.sorted_ascending()
    if len(candles) < 2:
        return True

    interval = timedelta(minutes=interval_minutes)
    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]
        expected_next = prev.identity.open_time + interval
        if curr.identity.open_time != expected_next:
            return False
    return True


def recovery_status(gap_status: GapStatus) -> str:
    """Return a human-readable recovery status."""
    if not gap_status.gaps_detected:
        return "CONTINUITY_VERIFIED_NO_GAPS"
    if gap_status.filled_count == gap_status.gap_count:
        return "ALL_GAPS_FILLED"
    if gap_status.filled_count > 0:
        return f"PARTIAL_RECOVERY_{gap_status.filled_count}_OF_{gap_status.gap_count}"
    return "CONTINUITY_BROKEN_CANNOT_RECOVER"
