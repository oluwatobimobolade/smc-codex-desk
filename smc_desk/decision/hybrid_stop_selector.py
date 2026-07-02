"""Hybrid structural stop selection for intraday SMC plans."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


PASS = "PASS"
REJECTED_NO_STRUCTURAL_STOP = "REJECTED_NO_STRUCTURAL_STOP"
REJECTED_REFINED_STOP_INSIDE_LIQUIDITY = "REJECTED_REFINED_STOP_INSIDE_LIQUIDITY"


def select_hybrid_structural_stop(
    *,
    direction: str,
    entry_style: str,
    active_poi: Mapping[str, Any] | None,
    sweep_extreme: Any = None,
    protected_extreme: Any = None,
    confirmation_swing: Any = None,
    nearby_liquidity: list[Any] | None = None,
) -> dict[str, Any]:
    direction = str(direction or "").lower()
    active_poi = _mapping(active_poi)
    nearby_liquidity = nearby_liquidity or []
    refined = str(entry_style).upper() in {"CONFIRMED", "REFINED", "FIVE_MINUTE_REFINEMENT_ALLOWED", "CONSERVATIVE_CONFIRMATION_REQUIRED"}

    if refined and confirmation_swing not in {None, ""}:
        swing = _decimal(confirmation_swing)
        if swing is None:
            return _result(REJECTED_NO_STRUCTURAL_STOP, None, "confirmation_swing", ["Confirmation swing could not be parsed."])
        if _inside_obvious_liquidity(swing, nearby_liquidity):
            return _result(REJECTED_REFINED_STOP_INSIDE_LIQUIDITY, None, "confirmation_swing", ["Refined stop sits inside obvious liquidity; require stronger confirmation."])
        return _result(PASS, swing, "confirmation_swing", ["Confirmed/refined entry may use the confirmation swing structural stop."])

    candidates = []
    if direction == "bearish":
        candidates.extend(_prices([active_poi.get("price_high"), sweep_extreme, protected_extreme]))
        stop = max(candidates) if candidates else None
        source = "above_poi_sweep_or_protected_high"
    elif direction == "bullish":
        candidates.extend(_prices([active_poi.get("price_low"), sweep_extreme, protected_extreme]))
        stop = min(candidates) if candidates else None
        source = "below_poi_sweep_or_protected_low"
    else:
        stop = None
        source = "unknown_direction"
    if stop is None:
        return _result(REJECTED_NO_STRUCTURAL_STOP, None, source, ["No POI, sweep, or protected structural stop anchor found."])
    return _result(PASS, stop, source, ["Aggressive entry uses full structural invalidation, not a fragile sniper stop."])


def _inside_obvious_liquidity(stop: Decimal, levels: list[Any]) -> bool:
    for level in levels:
        price = _decimal(level)
        if price is None:
            continue
        tolerance = max(abs(price) * Decimal("0.0005"), Decimal("0.00000001"))
        if abs(stop - price) <= tolerance:
            return True
    return False


def _prices(values: list[Any]) -> list[Decimal]:
    parsed: list[Decimal] = []
    for value in values:
        price = _decimal(value)
        if price is not None:
            parsed.append(price)
    return parsed


def _result(status: str, stop: Decimal | None, source: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "stop_loss": None if stop is None else str(stop),
        "stop_source": source,
        "stop_loss_style": "hybrid_structural",
        "account_risk_decision": "disabled",
        "position_sizing": "disabled",
        "reasons": reasons,
    }


def _decimal(value: Any) -> Decimal | None:
    try:
        if value in {None, ""}:
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

