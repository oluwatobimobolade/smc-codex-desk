"""Trader-grade SMC thesis writer with evidence links."""
from __future__ import annotations

from typing import Any, Mapping


FORBIDDEN_LIVE_ENTRY_WORDS = ("guaranteed", "100%", "risk capital now", "execute live", "paper trade now")


def build_smc_thesis_v2(
    *,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    structure_hierarchy: Mapping[str, Mapping[str, Any]],
    timeframe_roles: Mapping[str, Any],
    pois_by_tf: Mapping[str, list[Mapping[str, Any]]],
    watch_state: Mapping[str, Any],
) -> dict[str, Any]:
    claims = [
        _claim("daily_context", "Daily Context", _daily_context(structure_hierarchy), ["structure_hierarchy.1d"]),
        _claim("four_hour_external_bias", "4H External Bias", _tf_bias("4h", structure_hierarchy), ["structure_hierarchy.4h.external_bias"]),
        _claim("one_hour_setup_story", "1H POI / Setup Story", _one_hour_story(structure_hierarchy, pois_by_tf, watch_state), ["structure_hierarchy.1h", "poi_lifecycle.1h", "watch_state.active_poi"]),
        _claim("fifteen_minute_condition", "15M Execution Condition", "15M is confirmation-only. It may confirm entry timing, but it cannot override 1H/4H external bias.", ["timeframe_roles.15m_role"]),
        _claim("liquidity_taken", "Liquidity Taken", _liquidity_text(structure_hierarchy, "taken"), ["structure_hierarchy.*.latest_external_break_id"]),
        _claim("liquidity_resting", "Liquidity Still Resting", _liquidity_text(structure_hierarchy, "resting"), ["structure_hierarchy.*.dealing_range"]),
        _claim("active_poi", "Active POI", _active_poi_text(watch_state), ["watch_state.active_poi", "poi_lifecycle"]),
        _claim("premium_discount", "Premium / Discount Location", _premium_discount_text(structure_hierarchy), ["structure_hierarchy.*.dealing_range.price_location"]),
        _claim("confirmation_needed", "Confirmation Needed", _confirmation_needed(watch_state), ["watch_state.final_state", "timeframe_roles.execution_role"]),
        _claim("invalidation", "Invalidation", _invalidation_text(watch_state), ["watch_state.active_poi", "structure_hierarchy.1h.protected_high", "structure_hierarchy.1h.protected_low"]),
        _claim("final_state", "Final State", f"`{watch_state.get('final_state')}` with final action `{watch_state.get('final_action')}`.", ["watch_state.final_state", "refusal.final_action"]),
        _claim("why_no_execution", "Why No Execution Now", _why_no_execution(cognitive_result, watch_state), ["refusal", "watch_state"]),
    ]
    payload = {
        "status": "PASS",
        "symbol": symbol,
        "schema": "smc_thesis_v2",
        "final_state": watch_state.get("final_state"),
        "final_action": watch_state.get("final_action"),
        "forbidden_language_present": _contains_forbidden_language(claims),
        "claims": claims,
        "claim_count": len(claims),
    }
    return payload


def render_smc_thesis_v2_markdown(payload: Mapping[str, Any]) -> str:
    lines = [f"# {payload.get('symbol')} SMC Thesis V2", ""]
    lines.append(f"Final state: `{payload.get('final_state')}`")
    lines.append(f"Final action: `{payload.get('final_action')}`")
    lines.append("")
    for claim in payload.get("claims", []):
        lines.append(f"## {claim['title']}")
        lines.append("")
        lines.append(claim["claim"])
        lines.append("")
        lines.append("Evidence:")
        lines.extend(f"- `{item}`" for item in claim["evidence"])
        lines.append("")
    return "\n".join(lines)


def assert_smc_thesis_v2_quality(payload: Mapping[str, Any]) -> None:
    required = {
        "daily_context",
        "four_hour_external_bias",
        "one_hour_setup_story",
        "fifteen_minute_condition",
        "liquidity_taken",
        "liquidity_resting",
        "active_poi",
        "premium_discount",
        "confirmation_needed",
        "invalidation",
        "final_state",
        "why_no_execution",
    }
    seen = {claim.get("claim_id") for claim in payload.get("claims", [])}
    missing = required - seen
    if missing:
        raise AssertionError(f"Thesis V2 missing required claims: {sorted(missing)}")
    for claim in payload.get("claims", []):
        if not claim.get("evidence"):
            raise AssertionError(f"Claim has no evidence: {claim}")
    if payload.get("forbidden_language_present"):
        raise AssertionError("Thesis V2 contains forbidden live-entry language.")


def _claim(claim_id: str, title: str, text: str, evidence: list[str]) -> dict[str, Any]:
    return {"claim_id": claim_id, "title": title, "claim": text, "evidence": evidence}


def _daily_context(hierarchy: Mapping[str, Mapping[str, Any]]) -> str:
    day = hierarchy.get("1d", {})
    bias = day.get("external_bias", "neutral")
    depth = day.get("depth_status", "unknown")
    return f"Daily external bias is `{bias}`. Depth status is `{depth}`, so shallow context must be labelled instead of assumed."


def _tf_bias(tf: str, hierarchy: Mapping[str, Mapping[str, Any]]) -> str:
    item = hierarchy.get(tf, {})
    return (
        f"{tf} external bias is `{item.get('external_bias', 'neutral')}`. "
        f"Phase: `{item.get('structure_phase', 'unknown')}`. "
        f"Latest external break: `{item.get('latest_external_break_id')}`."
    )


def _one_hour_story(
    hierarchy: Mapping[str, Mapping[str, Any]],
    pois_by_tf: Mapping[str, list[Mapping[str, Any]]],
    watch_state: Mapping[str, Any],
) -> str:
    one_h = hierarchy.get("1h", {})
    active = watch_state.get("active_poi")
    if isinstance(active, Mapping) and active.get("timeframe") == "1h":
        poi_text = (
            f"{active.get('kind')} {active.get('price_low')} - {active.get('price_high')} "
            f"(selected rank {active.get('selection_rank', 'n/a')})"
        )
    else:
        selection = watch_state.get("poi_selection") if isinstance(watch_state.get("poi_selection"), Mapping) else {}
        parent = (selection.get("parent_scope_pois") or [])[:1]
        rejected = (selection.get("rejected_pois") or [])[:1]
        if parent:
            item = parent[0]
            poi_text = (
                f"no active 1H POI; parent-scope {item.get('kind')} "
                f"{item.get('price_low')} - {item.get('price_high')} is not active "
                f"because {item.get('rejection_reason')}"
            )
        elif rejected:
            item = rejected[0]
            poi_text = (
                f"no active 1H POI; rejected {item.get('kind')} "
                f"{item.get('price_low')} - {item.get('price_high')} because {item.get('rejection_reason')}"
            )
        else:
            poi_text = "none"
    return (
        f"1H external bias is `{one_h.get('external_bias', 'neutral')}` while internal state is "
        f"`{one_h.get('internal_state', 'unknown')}`. Selected 1H setup POI: `{poi_text}`."
    )


def _liquidity_text(hierarchy: Mapping[str, Mapping[str, Any]], mode: str) -> str:
    if mode == "taken":
        ids = [item.get("latest_external_break_id") for item in hierarchy.values() if item.get("latest_external_break_id")]
        return "Recent structure/liquidity break evidence: " + (", ".join(ids[-4:]) if ids else "none recorded.")
    ranges = [item.get("dealing_range") for item in hierarchy.values() if item.get("dealing_range")]
    if not ranges:
        return "No complete dealing range was available for resting liquidity classification."
    latest = ranges[-1]
    return f"External range liquidity remains near high `{latest.get('range_high')}` and low `{latest.get('range_low')}`."


def _active_poi_text(watch_state: Mapping[str, Any]) -> str:
    poi = watch_state.get("active_poi")
    if not poi:
        return "No certified active POI was selected; state must remain watch/review, not execute."
    return (
        f"Selected `{poi.get('timeframe')}` `{poi.get('kind')}` POI "
        f"`{poi.get('price_low')}` - `{poi.get('price_high')}`, relation `{poi.get('price_relation')}`."
    )


def _premium_discount_text(hierarchy: Mapping[str, Mapping[str, Any]]) -> str:
    locations = []
    for tf, item in hierarchy.items():
        dr = item.get("dealing_range") or {}
        if dr.get("price_location"):
            locations.append(f"{tf}: {dr.get('price_location')}")
    return "Price location by dealing range: " + (", ".join(locations) if locations else "not enough range evidence.")


def _confirmation_needed(watch_state: Mapping[str, Any]) -> str:
    direction = watch_state.get("direction", "neutral")
    if not watch_state.get("active_poi"):
        return "No 15M entry confirmation is actionable until a protected-range-valid active POI exists."
    if direction == "bearish":
        return "Need 15M bearish confirmation from the active supply/POI before any short thesis could be considered."
    if direction == "bullish":
        return "Need 15M bullish confirmation from the active demand/POI before any long thesis could be considered."
    return "Need clearer HTF/POI structure before any 15M confirmation is meaningful."


def _invalidation_text(watch_state: Mapping[str, Any]) -> str:
    poi = watch_state.get("active_poi")
    if not poi:
        return "No POI invalidation can be certified because no active POI was selected."
    if poi.get("direction") == "bearish":
        return f"Bearish watch invalidates if price accepts above POI high `{poi.get('price_high')}` / protected high."
    return f"Bullish watch invalidates if price accepts below POI low `{poi.get('price_low')}` / protected low."


def _why_no_execution(cognitive_result: Mapping[str, Any], watch_state: Mapping[str, Any]) -> str:
    refusal = cognitive_result.get("refusal") or {}
    reasons = refusal.get("reasons") or watch_state.get("reasons") or []
    readiness = cognitive_result.get("execution_readiness") or {}
    move_quality = cognitive_result.get("inducement_continuation") or {}
    continuation = move_quality.get("continuation_confirmed_if") or []
    inducement = move_quality.get("inducement_confirmed_if") or []
    parts = [
        "No execution because final action is observe-only and confirmation is incomplete.",
        f"Execution-readiness state: `{readiness.get('state', 'unknown')}`.",
        f"Move-quality state: `{move_quality.get('state', 'unknown')}`.",
    ]
    if continuation:
        parts.append("Continuation confirms only if: " + "; ".join(map(str, continuation[:3])) + ".")
    if inducement:
        parts.append("Inducement/reclaim risk confirms if: " + "; ".join(map(str, inducement[:3])) + ".")
    if reasons:
        parts.append("Reasons: " + "; ".join(map(str, reasons[:4])) + ".")
    return " ".join(parts)


def _contains_forbidden_language(claims: list[Mapping[str, Any]]) -> bool:
    haystack = " ".join(str(claim.get("claim", "")).lower() for claim in claims)
    return any(term in haystack for term in FORBIDDEN_LIVE_ENTRY_WORDS)
