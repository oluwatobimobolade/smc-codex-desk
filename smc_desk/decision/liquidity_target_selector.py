"""Setup-dependent liquidity target selection."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


PASS = "PASS"
REJECTED_NO_VALID_LIQUIDITY_TARGET = "REJECTED_NO_VALID_LIQUIDITY_TARGET"
REJECTED_TARGET_CONFLICTS_WITH_MODEL = "REJECTED_TARGET_CONFLICTS_WITH_MODEL"


def select_liquidity_targets(
    *,
    setup_model: Mapping[str, Any] | None,
    structure_hierarchy: Mapping[str, Any] | None,
    active_poi: Mapping[str, Any] | None = None,
    current_price: Any = None,
    invalidation: Mapping[str, Any] | None = None,
    entry_timeframe: str = "15m",
    max_targets: int = 3,
) -> dict[str, Any]:
    setup_model = _mapping(setup_model)
    structure_hierarchy = _mapping(structure_hierarchy)
    active_poi = _mapping(active_poi)
    invalidation = _mapping(invalidation)
    direction = str(setup_model.get("direction") or active_poi.get("direction") or "").lower()
    setup_timeframe = str(setup_model.get("setup_timeframe") or active_poi.get("timeframe") or "1h")
    invalidation_price = _decimal(invalidation.get("price"))
    current = _decimal(current_price)
    candidates = _target_candidates(direction=direction, setup_timeframe=setup_timeframe, hierarchy=structure_hierarchy)
    if not candidates:
        return _result(REJECTED_NO_VALID_LIQUIDITY_TARGET, [], setup_timeframe, entry_timeframe, ["No structural liquidity target found for active setup."])

    valid: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for candidate in candidates:
        price = _decimal(candidate.get("price"))
        if price is None:
            continue
        conflict_reason = _target_conflict(direction, price, invalidation_price, current)
        if conflict_reason:
            rejected = dict(candidate)
            rejected["rejection_reason"] = conflict_reason
            conflicts.append(rejected)
            continue
        valid.append(candidate)

    if valid:
        return _result(PASS, valid[:max_targets], setup_timeframe, entry_timeframe, ["Target selected from active setup liquidity, not from entry timeframe."])
    if conflicts:
        return _result(REJECTED_TARGET_CONFLICTS_WITH_MODEL, [], setup_timeframe, entry_timeframe, ["Candidate liquidity target conflicts with the active model."], rejected_targets=conflicts)
    return _result(REJECTED_NO_VALID_LIQUIDITY_TARGET, [], setup_timeframe, entry_timeframe, ["No valid target survived doctrine filters."])


def _target_candidates(*, direction: str, setup_timeframe: str, hierarchy: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    ordered_tfs = _ordered_timeframes(setup_timeframe)
    for priority_base, tf in enumerate(ordered_tfs, start=1):
        item = _mapping(hierarchy.get(tf))
        dr = _mapping(item.get("dealing_range"))
        if direction == "bearish":
            fields = [
                ("external_range_low", "previous structural low / sell-side liquidity"),
                ("protected_low", "protected sell-side liquidity"),
                ("range_low", "dealing-range sell-side liquidity"),
                ("equal_lows", "equal lows / clustered sell-side liquidity"),
                ("previous_day_low", "previous day low liquidity"),
                ("session_low", "session low liquidity"),
                ("fvg_fill_below", "imbalance/FVG fill below"),
                ("opposing_htf_demand", "opposing HTF demand"),
            ]
        elif direction == "bullish":
            fields = [
                ("external_range_high", "previous structural high / buy-side liquidity"),
                ("protected_high", "protected buy-side liquidity"),
                ("range_high", "dealing-range buy-side liquidity"),
                ("equal_highs", "equal highs / clustered buy-side liquidity"),
                ("previous_day_high", "previous day high liquidity"),
                ("session_high", "session high liquidity"),
                ("fvg_fill_above", "imbalance/FVG fill above"),
                ("opposing_htf_supply", "opposing HTF supply"),
            ]
        else:
            return []
        for offset, (field, reason) in enumerate(fields):
            value = item.get(field)
            if value in {None, ""}:
                value = dr.get(field)
            for price in _prices(value):
                candidates.append({
                    "price": str(price),
                    "reason": reason,
                    "source": field,
                    "timeframe": tf,
                    "priority": priority_base * 10 + offset,
                    "entry_timeframe": "not_target_authority",
                })
    return _unique_price_candidates(candidates)


def _target_conflict(direction: str, target: Decimal, invalidation: Decimal | None, current: Decimal | None) -> str | None:
    if direction == "bearish":
        if invalidation is not None and target >= invalidation:
            return "bearish_target_requires_bullish_invalidation_first"
        if current is not None and target >= current:
            return "bearish_target_is_not_below_current_price"
    elif direction == "bullish":
        if invalidation is not None and target <= invalidation:
            return "bullish_target_requires_bearish_invalidation_first"
        if current is not None and target <= current:
            return "bullish_target_is_not_above_current_price"
    return None


def _ordered_timeframes(setup_timeframe: str) -> list[str]:
    order = []
    for tf in (setup_timeframe, "1h", "4h", "15m", "1d"):
        if tf and tf not in order:
            order.append(tf)
    return order


def _prices(value: Any) -> list[Decimal]:
    if isinstance(value, (list, tuple)):
        return [price for item in value if (price := _decimal(item)) is not None]
    price = _decimal(value)
    return [] if price is None else [price]


def _unique_price_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = str(candidate.get("price"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _result(status: str, targets: list[dict[str, Any]], setup_timeframe: str, entry_timeframe: str, reasons: list[str], *, rejected_targets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "target_selection": "setup_dependent_liquidity",
        "setup_timeframe": setup_timeframe,
        "entry_timeframe": entry_timeframe,
        "entry_timeframe_is_not_target_authority": True,
        "targets": targets,
        "rejected_targets": rejected_targets or [],
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

