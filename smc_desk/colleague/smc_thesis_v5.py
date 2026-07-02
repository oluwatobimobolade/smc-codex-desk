"""SMC Thesis V5: narrative-authority-first trader sequence."""
from __future__ import annotations

from typing import Any, Mapping


FORBIDDEN_LIVE_ENTRY_WORDS = (
    "guaranteed",
    "100%",
    "execute live",
    "paper trade now",
    "risk capital now",
    "enter now",
)

REQUIRED_SEQUENCE = [
    "htf_context",
    "liquidity_taken",
    "displacement",
    "active_poi",
    "current_state",
    "continuation_condition",
    "inducement_condition",
    "invalidation",
    "final_observe_only_state",
]


def build_smc_thesis_v5(
    *,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    narrative_authority: Mapping[str, Any],
) -> dict[str, Any]:
    claims = [
        _claim("htf_context", "HTF Context", _htf_context(cognitive_result, narrative_authority), ["smc_narrative_authority.official_bias", "structure_hierarchy.4h", "structure_hierarchy.1h"]),
        _claim("liquidity_taken", "Liquidity Taken", _liquidity_taken(cognitive_result), ["structure_hierarchy.*.latest_external_break_id", "liquidity_sequence"]),
        _claim("displacement", "Displacement", _displacement(cognitive_result, narrative_authority), ["inducement_continuation", "perception_by_tf.15m.structure_breaks"]),
        _claim("active_poi", "Active POI", _active_poi(narrative_authority), ["smc_narrative_authority.official_active_poi"]),
        _claim("current_state", "Current State", _current_state(narrative_authority), ["smc_narrative_authority.official_state", "execution_readiness"]),
        _claim("continuation_condition", "Continuation Condition", _conditions(narrative_authority, "continuation_confirmed_if"), ["smc_narrative_authority.continuation_confirmed_if"]),
        _claim("inducement_condition", "Inducement Condition", _conditions(narrative_authority, "inducement_confirmed_if"), ["smc_narrative_authority.inducement_confirmed_if"]),
        _claim("invalidation", "Invalidation", _invalidation(narrative_authority), ["smc_narrative_authority.official_invalidation"]),
        _claim("final_observe_only_state", "Final Observe-Only State", _final_state(narrative_authority), ["smc_narrative_authority.official_trade_plan_state", "smc_narrative_authority.show_trade_box"]),
    ]
    payload = {
        "schema": "smc_thesis_v5",
        "status": "PASS",
        "symbol": symbol,
        "final_action": cognitive_result.get("final_action"),
        "official_model": narrative_authority.get("official_model"),
        "official_state": narrative_authority.get("official_state"),
        "official_trade_plan_state": narrative_authority.get("official_trade_plan_state"),
        "show_trade_box": bool(narrative_authority.get("show_trade_box")),
        "forbidden_language_present": _contains_forbidden_language(claims),
        "claim_sequence": [claim["claim_id"] for claim in claims],
        "claims": claims,
        "claim_count": len(claims),
    }
    return payload


def render_smc_thesis_v5_markdown(payload: Mapping[str, Any]) -> str:
    lines = [f"# {payload.get('symbol')} SMC Thesis V5", ""]
    lines.append(f"Official model: `{payload.get('official_model')}`")
    lines.append(f"Official state: `{payload.get('official_state')}`")
    lines.append(f"Trade-plan state: `{payload.get('official_trade_plan_state')}`")
    lines.append(f"Show trade box: `{payload.get('show_trade_box')}`")
    lines.append("")
    for claim in payload.get("claims", []) or []:
        lines.append(f"## {claim['title']}")
        lines.append("")
        lines.append(str(claim["claim"]))
        lines.append("")
        lines.append("Evidence:")
        lines.extend(f"- `{item}`" for item in claim["evidence"])
        lines.append("")
    return "\n".join(lines)


def assert_smc_thesis_v5_quality(payload: Mapping[str, Any]) -> None:
    if payload.get("claim_sequence") != REQUIRED_SEQUENCE:
        raise AssertionError("Thesis V5 does not follow the required SMC sequence.")
    for claim in payload.get("claims", []) or []:
        if not claim.get("evidence"):
            raise AssertionError(f"Thesis V5 claim has no evidence: {claim}")
    if payload.get("forbidden_language_present"):
        raise AssertionError("Thesis V5 contains forbidden live-entry language.")
    if payload.get("official_trade_plan_state") != "TRADE_PLAN_READY" and payload.get("show_trade_box"):
        raise AssertionError("Thesis V5 cannot show trade box for watch-only state.")


def _claim(claim_id: str, title: str, text: str, evidence: list[str]) -> dict[str, Any]:
    return {"claim_id": claim_id, "title": title, "claim": text, "evidence": evidence}


def _htf_context(cognitive: Mapping[str, Any], authority: Mapping[str, Any]) -> str:
    hierarchy = cognitive.get("structure_hierarchy") or {}
    h4 = hierarchy.get("4h", {}) if isinstance(hierarchy, Mapping) else {}
    h1 = hierarchy.get("1h", {}) if isinstance(hierarchy, Mapping) else {}
    return (
        f"The official bias is `{authority.get('official_bias')}`. "
        f"4H external bias is `{h4.get('external_bias', 'unknown')}` and 1H external bias is `{h1.get('external_bias', 'unknown')}`."
    )


def _liquidity_taken(cognitive: Mapping[str, Any]) -> str:
    hierarchy = cognitive.get("structure_hierarchy") or {}
    ids = []
    if isinstance(hierarchy, Mapping):
        for tf in ("4h", "1h", "15m"):
            item = hierarchy.get(tf, {}) or {}
            if item.get("latest_external_break_id"):
                ids.append(f"{tf}:{item.get('latest_external_break_id')}")
    sequence = cognitive.get("liquidity_sequence") or {}
    if ids:
        return "Relevant liquidity/structure evidence: " + ", ".join(ids[-4:]) + "."
    if sequence:
        return "Liquidity sequence exists, but no single external break dominates the official story."
    return "No decisive liquidity-taken event is promoted into the official story."


def _displacement(cognitive: Mapping[str, Any], authority: Mapping[str, Any]) -> str:
    move = cognitive.get("inducement_continuation") or {}
    evidence = move.get("evidence") if isinstance(move, Mapping) else {}
    count = evidence.get("same_direction_15m_break_count") if isinstance(evidence, Mapping) else None
    return (
        f"Move-quality state is `{move.get('state', 'unknown') if isinstance(move, Mapping) else 'unknown'}`. "
        f"Same-direction 15M break count is `{count}`. Official state is `{authority.get('official_state')}`."
    )


def _active_poi(authority: Mapping[str, Any]) -> str:
    poi = authority.get("official_active_poi") or {}
    if not poi:
        return "No official POI is certified; the chart must remain review/watch only."
    return (
        f"Official watch zone is `{poi.get('zone_label')}` with validity `{poi.get('validity_status')}` "
        f"and relation `{poi.get('price_relation')}`."
    )


def _current_state(authority: Mapping[str, Any]) -> str:
    confirmation = authority.get("official_confirmation_needed") or {}
    return (
        f"Official state is `{authority.get('official_state')}`. "
        f"Confirmation needed: {confirmation.get('summary', 'not specified')}."
    )


def _conditions(authority: Mapping[str, Any], key: str) -> str:
    items = [str(item) for item in authority.get(key, []) or []]
    if not items:
        return "No condition has been promoted to official status yet."
    return "; ".join(items[:3]) + "."


def _invalidation(authority: Mapping[str, Any]) -> str:
    invalidation = authority.get("official_invalidation") or {}
    if not invalidation:
        return "No official invalidation is certified."
    return f"Invalidation is `{invalidation.get('condition')}`. This is a watch invalidation, not an executable stop loss."


def _final_state(authority: Mapping[str, Any]) -> str:
    if authority.get("official_trade_plan_state") == "TRADE_PLAN_READY":
        return "Trade plan is ready according to narrative authority."
    return (
        f"Final state remains observe-only: `{authority.get('official_trade_plan_state')}`. "
        "No entry, stop loss, or take-profit trade box is allowed."
    )


def _contains_forbidden_language(claims: list[Mapping[str, Any]]) -> bool:
    haystack = " ".join(str(claim.get("claim", "")).lower() for claim in claims)
    return any(term in haystack for term in FORBIDDEN_LIVE_ENTRY_WORDS)
