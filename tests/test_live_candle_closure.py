"""WP-0017B tests: continuous candle-close monitoring.

Tests for closed_candle_store, reconciliation, gap_recovery, and
live_candle_coordinator.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
    compute_missing_intervals,
    verify_continuity,
    recovery_status,
    GapStatus,
)
from smc_desk.data.live_candle_coordinator import (
    LiveCandleCoordinator,
    StreamStatus,
    ProvisionalState,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _identity(t: datetime, tf: str = "15m") -> CandleIdentity:
    return CandleIdentity("BINANCE", "perpetual", "BTCUSDT", tf, t)


def _candle(t: datetime, close: Decimal = Decimal("50000")) -> ClosedCandle:
    return ClosedCandle(
        identity=_identity(t),
        open_price=close - Decimal("100"),
        high=close + Decimal("50"),
        low=close - Decimal("100"),
        close_price=close,
        volume=Decimal("100"),
        close_time=t + timedelta(minutes=15),
        source="websocket",
        received_at=t + timedelta(minutes=15),
        reconciled=False,
    )


# ── ClosedCandleStore tests ──

class TestClosedCandleStore:
    def test_insert_returns_true_for_new_candle(self):
        store = ClosedCandleStore()
        inserted = store.insert(_candle(NOW))
        assert inserted is True
        assert store.count == 1

    def test_insert_returns_false_for_exact_duplicate(self):
        store = ClosedCandleStore()
        c = _candle(NOW)
        store.insert(c)
        # Same identity and same OHLCV — should be silently accepted
        inserted = store.insert(c)
        assert inserted is False
        assert store.count == 1  # still only one

    def test_insert_raises_on_conflicting_duplicate(self):
        store = ClosedCandleStore()
        c1 = _candle(NOW, Decimal("50000"))
        c2 = _candle(NOW, Decimal("50100"))  # same identity, different close
        store.insert(c1)
        with pytest.raises(ConflictError) as exc:
            store.insert(c2)
        assert "conflict" in str(exc.value).lower()

    def test_same_ohlcv_but_different_source_still_duplicate(self):
        store = ClosedCandleStore()
        c1 = _candle(NOW)
        c2 = ClosedCandle(
            identity=_identity(NOW),
            open_price=c1.open, high=c1.high, low=c1.low,
            close_price=c1.close, volume=c1.volume,
            close_time=c1.close_time,
            source="rest_reconciliation",  # different source
            received_at=NOW + timedelta(minutes=16),
            reconciled=True,
        )
        store.insert(c1)
        assert store.insert(c2) is False  # same OHLCV, silently accepted

    def test_latest_returns_last_inserted(self):
        store = ClosedCandleStore()
        c1 = _candle(NOW)
        c2 = _candle(NOW + timedelta(minutes=15), Decimal("50100"))
        store.insert(c1)
        store.insert(c2)
        assert store.latest().close == Decimal("50100")

    def test_sorted_ascending(self):
        store = ClosedCandleStore()
        c1 = _candle(NOW + timedelta(minutes=30))
        c2 = _candle(NOW)  # earlier
        store.insert(c1)
        store.insert(c2)
        sorted_candles = store.sorted_ascending()
        assert sorted_candles[0].identity.open_time == NOW
        assert sorted_candles[1].identity.open_time == NOW + timedelta(minutes=30)

    def test_count_and_has(self):
        store = ClosedCandleStore()
        store.insert(_candle(NOW))
        assert store.count == 1
        assert store.has(_identity(NOW))
        assert not store.has(_identity(NOW + timedelta(minutes=15)))


# ── Reconciliation tests ──

class TestReconciliation:
    def test_exact_match_succeeds(self):
        store = ClosedCandleStore()
        ws = _candle(NOW)
        rest = _candle(NOW)  # identical
        result = reconcile_ws_candle(ws, [rest], store)
        assert result.is_match
        assert store.count == 1

    def test_mismatch_blocks(self):
        store = ClosedCandleStore()
        ws = _candle(NOW, Decimal("50000"))
        rest = _candle(NOW, Decimal("50100"))
        result = reconcile_ws_candle(ws, [rest], store)
        assert result.is_blocked
        assert result.status == ReconciliationStatus.MISMATCH
        assert store.count == 0

    def test_missing_rest_candle(self):
        store = ClosedCandleStore()
        ws = _candle(NOW)
        rest = [_candle(NOW + timedelta(minutes=15))]  # different candle
        result = reconcile_ws_candle(ws, rest, store)
        assert result.status == ReconciliationStatus.MISSING

    def test_duplicate_ws_candle_silently_accepted(self):
        store = ClosedCandleStore()
        ws = _candle(NOW)
        rest = [_candle(NOW)]
        reconcile_ws_candle(ws, rest, store)
        # Send the same candle again
        result = reconcile_ws_candle(ws, rest, store)
        assert result.status == ReconciliationStatus.DUPLICATE
        assert store.count == 1

    def test_conflict_with_existing_store_entry(self):
        store = ClosedCandleStore()
        # Pre-populate store with a different candle at the same identity
        existing = _candle(NOW, Decimal("50000"))
        store.insert(existing)
        ws = _candle(NOW, Decimal("50100"))
        rest = [_candle(NOW, Decimal("50100"))]  # REST matches WS, but store has different
        result = reconcile_ws_candle(ws, rest, store)
        assert result.status == ReconciliationStatus.MISMATCH


# ── Gap recovery tests ──

class TestGapRecovery:
    def _build_store(self, count: int, start: datetime = NOW) -> ClosedCandleStore:
        store = ClosedCandleStore()
        for i in range(count):
            t = start + timedelta(minutes=15 * i)
            store.insert(_candle(t, Decimal("50000") + Decimal(i)))
        return store

    def test_verify_continuity_on_contiguous_store(self):
        store = self._build_store(10)
        assert verify_continuity(store)

    def test_verify_continuity_detects_gap(self):
        store = self._build_store(5)
        # Insert a candle with a 30-minute gap instead of 15
        gap_candle = _candle(NOW + timedelta(minutes=90), Decimal("50010"))
        store.insert(gap_candle)
        assert not verify_continuity(store)

    def test_compute_missing_intervals_finds_gaps(self):
        store = self._build_store(5)  # 00-60 in 15m steps
        # Server time is 2 hours later — should find gaps
        server = NOW + timedelta(minutes=120)
        missing = compute_missing_intervals(store, server)
        assert len(missing) > 0

    def test_no_missing_when_up_to_date(self):
        store = self._build_store(4)  # 00-45
        server = NOW + timedelta(minutes=60)  # just past the last candle
        missing = compute_missing_intervals(store, server)
        assert len(missing) == 0

    def test_recovery_status_all_filled(self):
        gs = GapStatus()
        gs.gaps_detected = True
        gs.gap_count = 3
        gs.filled_count = 3
        assert recovery_status(gs) == "ALL_GAPS_FILLED"

    def test_recovery_status_broken(self):
        gs = GapStatus()
        gs.gaps_detected = True
        gs.gap_count = 3
        gs.filled_count = 0
        assert "CONTINUITY_BROKEN" in recovery_status(gs)


# ── LiveCandleCoordinator tests ──

class TestLiveCandleCoordinator:
    def test_bootstrap_loads_candles(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        candles = [_candle(NOW + timedelta(minutes=15 * i)) for i in range(10)]
        inserted = coord.bootstrap_from_rest(candles)
        assert inserted == 10
        assert coord.candle_count() == 10

    def test_forming_candle_updates_provisional_only(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        coord.bootstrap_from_rest([_candle(NOW - timedelta(minutes=15))])
        assert coord.candle_count() == 1

        coord.handle_forming_candle(
            open_time=NOW,
            close=Decimal("50100"),
            high=Decimal("50150"),
            low=Decimal("50050"),
            direction_hint="bullish",
        )
        # Provisional state updated
        assert coord.provisional.current_price == Decimal("50100")
        # Store should NOT have the forming candle
        assert coord.candle_count() == 1
        assert coord.status == StreamStatus.STREAMING

    def test_closed_candidate_matched_commits(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        coord.bootstrap_from_rest([_candle(NOW - timedelta(minutes=15))])

        ws = _candle(NOW)
        rest = [_candle(NOW)]
        result = coord.handle_closed_candidate(ws, rest)
        assert result.is_match
        assert coord.candle_count() == 2

    def test_closed_candidate_mismatch_blocks(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        ws = _candle(NOW, Decimal("50000"))
        rest = [_candle(NOW, Decimal("50200"))]  # mismatch
        result = coord.handle_closed_candidate(ws, rest)
        assert result.is_blocked
        assert coord.candle_count() == 0

    def test_on_new_confirmed_candle_callback(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        received: list = []

        def callback(candle):
            received.append(candle)

        coord.on_new_confirmed_candle = callback
        ws = _candle(NOW)
        rest = [_candle(NOW)]
        coord.handle_closed_candidate(ws, rest)
        assert len(received) == 1
        assert received[0].close == Decimal("50000")

    def test_continuity_after_bootstrap(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        candles = [_candle(NOW + timedelta(minutes=15 * i)) for i in range(5)]
        coord.bootstrap_from_rest(candles)
        assert coord.continuity_ok()

    def test_gap_detection_after_skip(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        # Insert first 3 candles, skip 1, then insert the 5th
        for i in [0, 1, 2, 4]:
            coord.store.insert(_candle(NOW + timedelta(minutes=15 * i)))
        assert not coord.continuity_ok()

    def test_summary_returns_expected_keys(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        coord.bootstrap_from_rest([_candle(NOW)])
        summary = coord.summary()
        for key in ("status", "symbol", "interval", "candle_count",
                     "continuity_verified", "provisional"):
            assert key in summary

    def test_recover_from_disconnect_fills_gaps(self):
        coord = LiveCandleCoordinator("BTCUSDT")
        # Only have 2 candles with a gap
        coord.store.insert(_candle(NOW))
        coord.store.insert(_candle(NOW + timedelta(minutes=45)))  # 30-min gap

        def fake_rest():
            return [
                _candle(NOW + timedelta(minutes=15 * i))
                for i in range(5)
            ]

        gs = coord.recover_from_disconnect(fake_rest)
        assert coord.candle_count() >= 2
        assert coord.continuity_ok()
