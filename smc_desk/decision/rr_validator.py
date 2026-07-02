"""Reward/risk validation for official intraday SMC trade plans."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from smc_desk.profile.smc_intraday_profile import SMC_INTRADAY_PROFILE


PASS = "PASS"
VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY = "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY"


def validate_rr(
    *,
    direction: str,
    entry: Any,
    stop_loss: Any,
    target: Any,
    minimum_rr: float | None = None,
    profile: Mapping[str, Any] = SMC_INTRADAY_PROFILE,
) -> dict[str, Any]:
    minimum = Decimal(str(minimum_rr if minimum_rr is not None else profile["minimum_rr"]))
    entry_d = _decimal(entry)
    stop_d = _decimal(stop_loss)
    target_d = _decimal(target)
    if entry_d is None or stop_d is None or target_d is None:
        return _result(VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, None, minimum, ["Entry, stop, and target are required before RR can pass."])

    if direction == "bearish":
        risk = stop_d - entry_d
        reward = entry_d - target_d
    elif direction == "bullish":
        risk = entry_d - stop_d
        reward = target_d - entry_d
    else:
        return _result(VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, None, minimum, ["No valid direction for RR calculation."])
    if risk <= 0 or reward <= 0:
        return _result(VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, None, minimum, ["Entry/stop/target geometry is invalid for the direction."])
    rr = reward / risk
    if rr < minimum:
        return _result(VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, rr, minimum, ["Valid direction, but RR is below the fixed 1:3 minimum."])
    return _result(PASS, rr, minimum, ["RR meets or exceeds the fixed 1:3 minimum."])


def _result(status: str, rr: Decimal | None, minimum: Decimal, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "rr": None if rr is None else float(round(rr, 4)),
        "minimum_rr": float(minimum),
        "reasons": reasons,
    }


def _decimal(value: Any) -> Decimal | None:
    try:
        if value in {None, ""}:
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

