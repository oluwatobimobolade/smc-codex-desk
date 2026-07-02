"""Entry style selection under the locked intraday SMC profile."""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.profile.smc_intraday_profile import SMC_INTRADAY_PROFILE


AGGRESSIVE_ENTRY_ALLOWED = "AGGRESSIVE_ENTRY_ALLOWED"
CONSERVATIVE_CONFIRMATION_REQUIRED = "CONSERVATIVE_CONFIRMATION_REQUIRED"
FIVE_MINUTE_REFINEMENT_ALLOWED = "FIVE_MINUTE_REFINEMENT_ALLOWED"
REJECTED_1M_ENTRY_FORBIDDEN = "REJECTED_1M_ENTRY_FORBIDDEN"


def select_entry_style(
    *,
    active_poi: Mapping[str, Any] | None,
    displacement: Mapping[str, Any] | None = None,
    liquidity_sweep: bool = False,
    rr: float | None = None,
    poi_width_pct: float | None = None,
    inducement_risk: bool = False,
    requested_timeframe: str | None = None,
    needs_refinement: bool = False,
    profile: Mapping[str, Any] = SMC_INTRADAY_PROFILE,
) -> dict[str, Any]:
    timeframe = requested_timeframe or str(profile["default_entry_timeframe"])
    if timeframe in set(profile.get("forbidden_entry_timeframes", ())):
        return _result(REJECTED_1M_ENTRY_FORBIDDEN, str(profile["default_entry_timeframe"]), None, ["1m is forbidden for official entries."])

    if timeframe == profile.get("optional_refinement_timeframe"):
        allowed = needs_refinement or (rr is not None and rr < float(profile["minimum_rr"]) + 0.35)
        state = FIVE_MINUTE_REFINEMENT_ALLOWED if allowed else CONSERVATIVE_CONFIRMATION_REQUIRED
        reason = "5m refinement is optional and only used to refine a 15m idea." if allowed else "5m is not the default entry authority."
        return _result(state, str(profile["default_entry_timeframe"]), str(profile["optional_refinement_timeframe"]) if allowed else None, [reason])

    active_poi = active_poi if isinstance(active_poi, Mapping) else {}
    displacement = displacement if isinstance(displacement, Mapping) else {}
    clean_poi = bool(active_poi) and str(active_poi.get("validity_status") or "") in {"", "VALID_ACTIVE_SETUP_POI"}
    strong_displacement = str(displacement.get("quality") or "").lower() in {"strong", "clean"} or bool(displacement.get("structure_broken"))
    rr_ok = rr is not None and rr >= float(profile["minimum_rr"])
    wide_or_messy = inducement_risk or (poi_width_pct is not None and poi_width_pct > 0.75)

    if clean_poi and liquidity_sweep and strong_displacement and rr_ok and not wide_or_messy:
        return _result(AGGRESSIVE_ENTRY_ALLOWED, timeframe, None, ["POI, sweep, displacement, invalidation, and RR are clean."])
    reasons = ["Conservative confirmation required until the chart proves rejection."]
    if wide_or_messy:
        reasons.append("POI width, messy action, or inducement risk makes aggressive entry unsuitable.")
    if not rr_ok:
        reasons.append("RR is not yet proven at 1:3 or better.")
    return _result(CONSERVATIVE_CONFIRMATION_REQUIRED, timeframe, "5m" if needs_refinement else None, reasons)


def _result(state: str, entry_timeframe: str, refinement_timeframe: str | None, reasons: list[str]) -> dict[str, Any]:
    return {
        "state": state,
        "entry_timeframe": entry_timeframe,
        "refinement_timeframe": refinement_timeframe,
        "default_entry_timeframe": "15m",
        "optional_refinement_timeframe": "5m",
        "forbidden_entry_timeframes": ["1m"],
        "reasons": reasons,
    }

