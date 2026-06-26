"""Exact-once closed-candle persistence using venue+symbol+timeframe+open_time identity.

A candle may be delivered multiple times through WebSocket reconnection,
REST re-fetch, or stream replay. This store guarantees:

- Save once: identical identity → no duplicate insert.
- Ignore exact duplicates: same OHLCV on re-insert is silently accepted.
- Report conflicting duplicates: different OHLCV for same identity raises ConflictError.
- Never advance the system twice for the same candle.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional


class CandleIdentity:
    """Immutable candle identity — venue + market + symbol + timeframe + open_time."""

    def __init__(
        self, venue: str, market_type: str, symbol: str, timeframe: str, open_time: datetime
    ):
        self.venue = venue
        self.market_type = market_type
        self.symbol = symbol
        self.timeframe = timeframe
        self.open_time = open_time

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.market_type}:{self.symbol}:{self.timeframe}:{self.open_time.isoformat()}"

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandleIdentity):
            return False
        return self.key == other.key


class ClosedCandle:
    """A verified closed candle with provenance metadata."""

    def __init__(
        self,
        identity: CandleIdentity,
        open_price: Decimal,
        high: Decimal,
        low: Decimal,
        close_price: Decimal,
        volume: Decimal,
        close_time: datetime,
        source: str,  # "websocket", "rest_reconciliation", "rest_bootstrap"
        received_at: datetime,
        reconciled: bool = False,
    ):
        self.identity = identity
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close_price
        self.volume = volume
        self.close_time = close_time
        self.source = source
        self.received_at = received_at
        self.reconciled = reconciled

    def matches_ohlcv(self, other: "ClosedCandle") -> bool:
        """Check if two candles have identical OHLCV values."""
        return (
            self.open == other.open
            and self.high == other.high
            and self.low == other.low
            and self.close == other.close
            and self.volume == other.volume
            and self.close_time == other.close_time
        )


class ConflictError(Exception):
    """Two candles with the same identity but different OHLCV values."""

    def __init__(self, existing: ClosedCandle, incoming: ClosedCandle):
        self.existing = existing
        self.incoming = incoming
        super().__init__(
            f"Candle conflict at {existing.identity.key}: "
            f"existing close={existing.close} vs incoming close={incoming.close}"
        )


class ClosedCandleStore:
    """Exact-once persistent candle store.

    Uses CandleIdentity as the primary key. Duplicate candidatess with matching
    OHLCV are silently accepted. Conflicting duplicates raise ConflictError.
    """

    def __init__(self):
        self._candles: Dict[str, ClosedCandle] = {}
        self._insert_order: List[ClosedCandle] = []

    def insert(self, candle: ClosedCandle) -> bool:
        """Insert a candle. Returns True if newly inserted, False if duplicate (same OHLCV).

        Raises ConflictError if a candle with the same identity but different OHLCV exists.
        """
        key = candle.identity.key
        if key in self._candles:
            existing = self._candles[key]
            if existing.matches_ohlcv(candle):
                return False  # exact duplicate, silently accepted
            else:
                raise ConflictError(existing, candle)

        self._candles[key] = candle
        self._insert_order.append(candle)
        return True

    def get(self, identity: CandleIdentity) -> Optional[ClosedCandle]:
        return self._candles.get(identity.key)

    def has(self, identity: CandleIdentity) -> bool:
        return identity.key in self._candles

    @property
    def count(self) -> int:
        return len(self._candles)

    @property
    def candles_in_order(self) -> List[ClosedCandle]:
        return list(self._insert_order)

    def latest(self) -> Optional[ClosedCandle]:
        return self._insert_order[-1] if self._insert_order else None

    def latest_n(self, n: int) -> List[ClosedCandle]:
        return self._insert_order[-n:] if self._insert_order else []

    def latest_open_time(self) -> Optional[datetime]:
        latest = self.latest()
        return latest.identity.open_time if latest else None

    def sorted_ascending(self) -> List[ClosedCandle]:
        return sorted(self._insert_order, key=lambda c: c.identity.open_time)
