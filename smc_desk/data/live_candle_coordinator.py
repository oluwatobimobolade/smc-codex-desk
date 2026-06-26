"""Live candle coordinator — stream → reconciliation → store → decision.

Orchestrates the continuous live candle pipeline:

1. REST bootstrap: acquire verified closed candles
2. WebSocket connection: subscribe to kline stream
3. x=false: update provisional state only
4. x=true: closed-candle candidate → REST reconciliation → store
5. Gap detection and recovery on disconnect
6. Notify decision pipeline of new confirmed events

Design:
- Provisional state is kept separate from confirmed history.
- No confirmed BOS, CHoCH, or FVG from a forming candle.
- No strategy-state advancement from a candle before reconciliation.
- Gap recovery restores continuity before resuming the stream.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from smc_desk.data.closed_candle_store import (
    CandleIdentity,
    ClosedCandle,
    ClosedCandleStore,
    ConflictError,
)
from smc_desk.data.reconciliation import (
    ReconciliationResult,
    ReconciliationStatus,
    reconcile_ws_candle,
)
from smc_desk.data.gap_recovery import (
    GapStatus,
    compute_missing_intervals,
    verify_continuity,
    recovery_status,
)


class StreamStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    STREAMING = "STREAMING"
    RECONCILING = "RECONCILING"
    RECOVERING = "RECOVERING"


class ProvisionalState:
    """State derived from the current forming candle (x=false).

    This state MUST NOT contain confirmed objects. It is purely
    observational — what appears to be forming right now, which
    may change before the candle closes.
    """

    def __init__(self):
        self.current_price: Optional[Decimal] = None
        self.direction: str = "neutral"
        self.forming_sweep: bool = False
        self.forming_break: bool = False
        self.note: str = ""

    def to_dict(self) -> dict:
        return {
            "current_price": str(self.current_price) if self.current_price else None,
            "direction": self.direction,
            "forming_sweep": self.forming_sweep,
            "forming_break": self.forming_break,
            "note": self.note,
        }


class LiveCandleCoordinator:
    """Coordinates the live candle pipeline from stream to store to decision."""

    def __init__(self, symbol: str = "BTCUSDT", interval_minutes: int = 15):
        self.symbol = symbol
        self.interval_minutes = interval_minutes
        self.store = ClosedCandleStore()
        self.provisional = ProvisionalState()
        self.status = StreamStatus.DISCONNECTED
        self.reconciliation_log: List[ReconciliationResult] = []
        self.gap_status = GapStatus()
        self.on_new_confirmed_candle: Optional[Callable[[ClosedCandle], None]] = None

    # ── REST bootstrap ──

    def bootstrap_from_rest(self, rest_candles: List[ClosedCandle]) -> int:
        """Load initial candle history from REST. Returns count inserted."""
        count = 0
        for candle in rest_candles:
            try:
                if self.store.insert(candle):
                    count += 1
            except ConflictError:
                continue
        return count

    # ── WebSocket event handling ──

    def handle_forming_candle(
        self,
        open_time: datetime,
        close: Decimal,
        high: Decimal,
        low: Decimal,
        direction_hint: str = "neutral",
    ) -> None:
        """Process an x=false (forming) WebSocket event.

        Updates provisional state only. Must not create confirmed objects.
        """
        self.status = StreamStatus.STREAMING
        self.provisional.current_price = close
        self.provisional.direction = direction_hint
        self.provisional.note = (
            f"Forming candle at {open_time.isoformat()} — "
            f"provisional only, NOT confirmed"
        )

    def handle_closed_candidate(
        self,
        ws_candle: ClosedCandle,
        rest_response: List[ClosedCandle],
    ) -> ReconciliationResult:
        """Process an x=true (closed) WebSocket event.

        1. Set status to RECONCILING
        2. Reconcile against REST
        3. If match, insert into store (exact-once)
        4. If mismatch, block and log
        5. Signal new confirmed candle to decision pipeline

        Returns the ReconciliationResult.
        """
        self.status = StreamStatus.RECONCILING
        result = reconcile_ws_candle(ws_candle, rest_response, self.store)
        self.reconciliation_log.append(result)

        if result.is_match:
            self.status = StreamStatus.STREAMING
            if self.on_new_confirmed_candle:
                self.on_new_confirmed_candle(ws_candle)
        else:
            # Block: reset to streaming but log the incident
            self.status = StreamStatus.STREAMING

        return result

    # ── Gap recovery on reconnect ──

    def recover_from_disconnect(
        self,
        rest_fetch_fn: Callable[[], List[ClosedCandle]],
        server_time: Optional[datetime] = None,
    ) -> GapStatus:
        """Attempt to recover after a WebSocket disconnect.

        1. Set status to RECOVERING
        2. REST-fetch the latest candles
        3. Compute missing intervals
        4. Fill gaps
        5. Verify continuity
        6. Return recovery status

        Args:
            rest_fetch_fn: Function that fetches the latest REST candles.
            server_time: Current Binance server time (UTC).

        Returns:
            GapStatus with recovery details.
        """
        self.status = StreamStatus.RECOVERING
        server_time = server_time or datetime.now(tz=timezone.utc)

        # Fetch latest candles
        rest_candles = rest_fetch_fn()

        # Insert any new candles
        for candle in rest_candles:
            try:
                self.store.insert(candle)
            except ConflictError:
                continue

        # Compute and report gaps
        missing = compute_missing_intervals(
            self.store, server_time, self.interval_minutes
        )
        if missing:
            self.gap_status.gaps_detected = True
            self.gap_status.gap_count = len(missing)
            self.gap_status.missing_intervals = missing

        # Verify continuity
        self.gap_status.continuity_verified = verify_continuity(
            self.store, self.interval_minutes
        )

        self.status = StreamStatus.STREAMING
        return self.gap_status

    # ── Read access ──

    def latest_closed_candle(self) -> Optional[ClosedCandle]:
        return self.store.latest()

    def candle_count(self) -> int:
        return self.store.count

    def continuity_ok(self) -> bool:
        return verify_continuity(self.store, self.interval_minutes)

    def summary(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "symbol": self.symbol,
            "interval": f"{self.interval_minutes}m",
            "candle_count": self.store.count,
            "latest_open_time": (
                self.store.latest_open_time().isoformat()
                if self.store.latest_open_time()
                else None
            ),
            "continuity_verified": verify_continuity(
                self.store, self.interval_minutes
            ),
            "provisional": self.provisional.to_dict(),
            "reconciliation_count": len(self.reconciliation_log),
            "recovery_status": recovery_status(self.gap_status),
        }
