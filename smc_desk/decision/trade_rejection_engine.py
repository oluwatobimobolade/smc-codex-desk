"""Hard rejection layer for official intraday SMC trade plans."""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.decision.entry_style_selector import REJECTED_1M_ENTRY_FORBIDDEN
from smc_desk.decision.liquidity_target_selector import (
    REJECTED_NO_VALID_LIQUIDITY_TARGET,
    REJECTED_TARGET_CONFLICTS_WITH_MODEL,
)
from smc_desk.decision.rr_validator import VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY
from smc_desk.decision.setup_classifier import NO_CLEAR_MODEL


REJECTION_CODES = {
    "REJECTED_NO_CLEAR_MODEL",
    "REJECTED_AGAINST_HTF_CONTROL",
    "LOW_QUALITY_CHOCH_NO_LIQUIDITY_SWEEP",
    "REJECTED_NO_DISPLACEMENT",
    "REJECTED_INVALID_POI",
    "MISSED_TRADE_NO_CHASE",
    "REJECTED_NO_VALID_LIQUIDITY_TARGET",
    "VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY",
    "REJECTED_TARGET_CONFLICTS_WITH_MODEL",
    "REJECTED_1M_ENTRY_FORBIDDEN",
    "POI_TOUCHED_AWAIT_CONFIRMATION",
    "WATCH_ONLY",
}


def evaluate_trade_rejections(
    *,
    setup_model: Mapping[str, Any] | None,
    htf_control: bool | str = True,
    liquidity_sweep: bool = True,
    displacement: bool | Mapping[str, Any] = True,
    active_poi: Mapping[str, Any] | None = None,
    move_state: str | None = None,
    target_selection: Mapping[str, Any] | None = None,
    rr_validation: Mapping[str, Any] | None = None,
    entry_style: Mapping[str, Any] | None = None,
    watch_state: str | None = None,
) -> dict[str, Any]:
    setup_model = _mapping(setup_model)
    active_poi = _mapping(active_poi)
    target_selection = _mapping(target_selection)
    rr_validation = _mapping(rr_validation)
    entry_style = _mapping(entry_style)

    codes: list[str] = []
    reasons: list[str] = []
    setup_type = str(setup_model.get("setup_type") or "")
    if setup_type in {"", NO_CLEAR_MODEL}:
        _add(codes, reasons, "REJECTED_NO_CLEAR_MODEL", "No clear doctrine-approved setup model.")
    if htf_control in {False, "against", "AGAINST"}:
        _add(codes, reasons, "REJECTED_AGAINST_HTF_CONTROL", "Setup trades against HTF control.")
    if setup_type.endswith(("REVERSAL_SHORT", "REVERSAL_LONG")) and not liquidity_sweep:
        _add(codes, reasons, "LOW_QUALITY_CHOCH_NO_LIQUIDITY_SWEEP", "Reversal/CHoCH model lacks a prior liquidity sweep.")
    if not _has_displacement(displacement):
        _add(codes, reasons, "REJECTED_NO_DISPLACEMENT", "No qualifying displacement after the liquidity event.")
    if active_poi and str(active_poi.get("validity_status") or "VALID_ACTIVE_SETUP_POI") != "VALID_ACTIVE_SETUP_POI":
        _add(codes, reasons, "REJECTED_INVALID_POI", "POI is invalid, mitigated, outside protected structure, or unrelated.")
    if str(move_state or "") == "MOVE_STARTED_NOT_CHASEABLE":
        _add(codes, reasons, "MISSED_TRADE_NO_CHASE", "Price already moved away without a retrace; do not chase.")
    target_status = str(target_selection.get("status") or "")
    if target_status == REJECTED_NO_VALID_LIQUIDITY_TARGET:
        _add(codes, reasons, "REJECTED_NO_VALID_LIQUIDITY_TARGET", "No setup-dependent liquidity target exists.")
    if target_status == REJECTED_TARGET_CONFLICTS_WITH_MODEL:
        _add(codes, reasons, "REJECTED_TARGET_CONFLICTS_WITH_MODEL", "Target conflicts with model/invalidation.")
    if str(rr_validation.get("status") or "") == VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY:
        _add(codes, reasons, VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, "Direction can be valid while RR is not tradable.")
    if str(entry_style.get("state") or "") == REJECTED_1M_ENTRY_FORBIDDEN:
        _add(codes, reasons, "REJECTED_1M_ENTRY_FORBIDDEN", "1m entries are forbidden by the intraday profile.")
    if watch_state in {"POI_TOUCHED_AWAIT_CONFIRMATION", "POI_TOUCHED_AWAIT_15M_CONFIRMATION"}:
        _add(codes, reasons, "POI_TOUCHED_AWAIT_CONFIRMATION", "POI has been touched but confirmation is still required.")

    status = codes[0] if codes else "WATCH_ONLY"
    if not codes:
        reasons.append("No hard rejection beyond observe-only gating.")
    return {
        "status": status,
        "hard_rejections": codes,
        "reasons": reasons,
        "trade_plan_state": "WATCH_ONLY" if status != "PASS" else "TRADE_PLAN_READY",
        "observe_only": True,
        "paper_execution": "disabled",
        "live_execution": "disabled",
        "capital_risk": 0,
    }


def _has_displacement(displacement: bool | Mapping[str, Any]) -> bool:
    if isinstance(displacement, Mapping):
        return bool(displacement.get("structure_broken") or displacement.get("direction"))
    return bool(displacement)


def _add(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    if code not in codes:
        codes.append(code)
        reasons.append(reason)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
