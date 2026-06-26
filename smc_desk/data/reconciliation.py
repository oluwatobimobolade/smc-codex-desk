"""Candle reconciliation: WS/REST matching for live candle authority.

After a WebSocket emits x=true, the closed candle must be independently
verified against the REST API before it enters confirmed history.

Statuses:
- WS_CLOSED_PENDING_RECONCILIATION: x=true received, waiting for REST
- WS_REST_MATCH: exact OHLCV match, commit to store
- WS_REST_MISMATCH: partial match, block the candle, create incident
- REST_CANDLE_MISSING: REST response doesn't contain the expected candle
- STALE_STREAM: WebSocket is behind REST (clock skew or disconnection)
- DUPLICATE_CLOSE_EVENT: same candle received multiple times via WS
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from smc_desk.data.closed_candle_store import ClosedCandle, ClosedCandleStore, ConflictError


class ReconciliationStatus(str, Enum):
    PENDING = "WS_CLOSED_PENDING_RECONCILIATION"
    MATCH = "WS_REST_MATCH"
    MISMATCH = "WS_REST_MISMATCH"
    MISSING = "REST_CANDLE_MISSING"
    STALE = "STALE_STREAM"
    DUPLICATE = "DUPLICATE_CLOSE_EVENT"


class ReconciliationResult:
    """Result of reconciling a WebSocket candle with REST."""

    def __init__(
        self,
        status: ReconciliationStatus,
        ws_candle: Optional[ClosedCandle] = None,
        rest_candle: Optional[ClosedCandle] = None,
        detail: str = "",
    ):
        self.status = status
        self.ws_candle = ws_candle
        self.rest_candle = rest_candle
        self.detail = detail

    @property
    def is_match(self) -> bool:
        return self.status == ReconciliationStatus.MATCH

    @property
    def is_blocked(self) -> bool:
        return self.status in (
            ReconciliationStatus.MISMATCH,
            ReconciliationStatus.MISSING,
            ReconciliationStatus.STALE,
        )

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "detail": self.detail,
            "ws_close": str(self.ws_candle.close) if self.ws_candle else None,
            "rest_close": str(self.rest_candle.close) if self.rest_candle else None,
        }


def reconcile_ws_candle(
    ws_candle: ClosedCandle,
    rest_candles: list[ClosedCandle],
    store: ClosedCandleStore,
) -> ReconciliationResult:
    """Reconcile a WebSocket closed candle against REST response.

    1. Find the matching REST candle by identity (open_time).
    2. Compare OHLCV exactly.
    3. If match, attempt to insert into the store.
    4. If store already has it (duplicate), accept silently.
    5. If mismatch, block and return MISMATCH status.

    Args:
        ws_candle: The candle received from WebSocket (x=true event).
        rest_candles: The latest REST response candles.
        store: The closed candle store for exact-once persistence.

    Returns:
        ReconciliationResult with status and detail.
    """
    # Find matching REST candle by identity
    rest_match: Optional[ClosedCandle] = None
    for rc in rest_candles:
        if rc.identity == ws_candle.identity:
            rest_match = rc
            break

    if rest_match is None:
        return ReconciliationResult(
            status=ReconciliationStatus.MISSING,
            ws_candle=ws_candle,
            detail="REST response does not contain the expected candle identity",
        )

    # Check OHLCV match
    if not ws_candle.matches_ohlcv(rest_match):
        return ReconciliationResult(
            status=ReconciliationStatus.MISMATCH,
            ws_candle=ws_candle,
            rest_candle=rest_match,
            detail="WS and REST OHLCV disagree",
        )

    # Attempt to insert into store (exact-once)
    try:
        inserted = store.insert(ws_candle)
        if not inserted:
            return ReconciliationResult(
                status=ReconciliationStatus.DUPLICATE,
                ws_candle=ws_candle,
                detail="Candle already in store (exact duplicate), silently accepted",
            )
    except ConflictError:
        return ReconciliationResult(
            status=ReconciliationStatus.MISMATCH,
            ws_candle=ws_candle,
            rest_candle=rest_match,
            detail="Candle identity exists in store with different OHLCV",
        )

    return ReconciliationResult(
        status=ReconciliationStatus.MATCH,
        ws_candle=ws_candle,
        rest_candle=rest_match,
        detail="WS and REST matched, candle committed to store",
    )
