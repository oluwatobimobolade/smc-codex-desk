"""SMC Thesis V7: OfficialSMCDecision-only thesis writer."""
from __future__ import annotations

from typing import Any, Mapping


REQUIRED_SEQUENCE = [
    "htf_1h_context",
    "liquidity_taken",
    "displacement",
    "active_poi",
    "current_state",
    "entry_condition",
    "structural_stop_logic",
    "target_liquidity_logic",
    "rr_status",
    "final_observe_only_state",
]

FORBIDDEN_LIVE_ENTRY_WORDS = (
    "guaranteed",
    "100%",
    "execute live",
    "paper trade now",
    "risk capital now",
    "enter now",
)


def build_smc_thesis_v7(*, official_decision: Mapping[str, Any]) -> dict[str, Any]:
    claims = [
        _claim("htf_1h_context", "HTF / 1H Context", _context(official_decision)),
        _claim("liquidity_taken", "Liquidity Taken", _liquidity_taken(official_decision)),
        _claim("displacement", "Displacement", _displacement(official_decision)),
        _claim("active_poi", "Active POI", _active_poi(official_decision)),
        _claim("current_state", "Current State", _current_state(official_decision)),
        _claim("entry_condition", "Entry Condition", _entry_condition(official_decision)),
        _claim("structural_stop_logic", "Structural Stop Logic", _stop_logic(official_decision)),
        _claim("target_liquidity_logic", "Target Liquidity Logic", _target_logic(official_decision)),
        _claim("rr_status", "RR Status", _rr_status(official_decision)),
        _claim("final_observe_only_state", "Final Observe-Only State", _final_state(official_decision)),
    ]
    payload = {
        "schema": "smc_thesis_v7",
        "status": "PASS",
        "symbol": official_decision.get("symbol"),
        "source": "OfficialSMCDecision",
        "official_model": official_decision.get("official_model"),
        "official_state": official_decision.get("official_state"),
        "trade_plan_state": official_decision.get("trade_plan_state") or official_decision.get("official_trade_plan_state"),
        "show_trade_box": bool(official_decision.get("show_trade_box")),
        "claim_sequence": [claim["claim_id"] for claim in claims],
        "claims": claims,
        "claim_count": len(claims),
        "forbidden_language_present": _contains_forbidden_language(claims),
    }
    assert_smc_thesis_v7_quality(payload)
    return payload


def render_smc_thesis_v7_markdown(payload: Mapping[str, Any]) -> str:
    lines = [f"# {payload.get('symbol')} SMC Thesis V7", ""]
    lines.append(f"Source: `{payload.get('source')}`")
    lines.append(f"Official model: `{payload.get('official_model')}`")
    lines.append(f"Official state: `{payload.get('official_state')}`")
    lines.append(f"Trade-plan state: `{payload.get('trade_plan_state')}`")
    lines.append(f"Show trade box: `{payload.get('show_trade_box')}`")
    lines.append("")
    for index, claim in enumerate(payload.get("claims", []) or [], start=1):
        lines.append(f"## {index}. {claim['title']}")
        lines.append("")
        lines.append(str(claim["claim"]))
        lines.append("")
        lines.append("Evidence:")
        lines.extend(f"- `{item}`" for item in claim["evidence"])
        lines.append("")
    return "\n".join(lines)


def assert_smc_thesis_v7_quality(payload: Mapping[str, Any]) -> None:
    if payload.get("source") != "OfficialSMCDecision":
        raise AssertionError("Thesis V7 must use only OfficialSMCDecision.")
    if payload.get("claim_sequence") != REQUIRED_SEQUENCE:
        raise AssertionError("Thesis V7 does not follow the required SMC doctrine sequence.")
    if payload.get("forbidden_language_present"):
        raise AssertionError("Thesis V7 contains forbidden live-entry language.")
    if payload.get("trade_plan_state") != "TRADE_PLAN_READY" and payload.get("show_trade_box"):
        raise AssertionError("Thesis V7 cannot show a trade box unless TRADE_PLAN_READY.")
    for claim in payload.get("claims", []) or []:
        if not claim.get("evidence"):
            raise AssertionError(f"Thesis V7 claim has no evidence: {claim}")


def _claim(claim_id: str, title: str, text: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "title": title,
        "claim": text,
        "evidence": evidence or [f"OfficialSMCDecision.{claim_id}"],
    }


def _context(decision: Mapping[str, Any]) -> str:
    return f"The official intraday model is `{decision.get('official_model')}` with `{decision.get('official_bias')}` bias."


def _liquidity_taken(decision: Mapping[str, Any]) -> str:
    items = [str(item) for item in decision.get("liquidity_taken", []) or []]
    return "; ".join(items) + "." if items else "No liquidity sweep is promoted into the official story yet."


def _displacement(decision: Mapping[str, Any]) -> str:
    displacement = decision.get("displacement") or {}
    return f"Displacement is `{displacement.get('quality', 'unknown')}`; structure broken = `{displacement.get('structure_broken')}`."


def _active_poi(decision: Mapping[str, Any]) -> str:
    poi = decision.get("active_poi") or {}
    if not poi:
        return "No active POI is certified, so the decision remains review/watch only."
    return f"Active POI is `{poi.get('zone_label')}` with validity `{poi.get('validity_status')}`."


def _current_state(decision: Mapping[str, Any]) -> str:
    return f"Current state is `{decision.get('official_state')}` and trade-plan state is `{decision.get('trade_plan_state')}`."


def _entry_condition(decision: Mapping[str, Any]) -> str:
    entry_style = decision.get("entry_style") or {}
    confirmation = decision.get("confirmation_needed") or []
    return f"Entry status is `{decision.get('entry_status')}`. Entry style: `{entry_style.get('state')}`. Needed: {'; '.join(map(str, confirmation[:3]))}."


def _stop_logic(decision: Mapping[str, Any]) -> str:
    stop = decision.get("stop_selection") or {}
    invalidation = decision.get("invalidation") or {}
    if decision.get("trade_plan_state") == "TRADE_PLAN_READY":
        return f"Official stop uses `{stop.get('stop_source')}`."
    return f"Watch invalidation is `{invalidation.get('condition', 'not certified')}`; this is not an executable stop loss."


def _target_logic(decision: Mapping[str, Any]) -> str:
    target_selection = decision.get("target_selection") or {}
    targets = target_selection.get("targets") or []
    if not targets:
        return f"Target status is `{target_selection.get('status', 'not_available')}`; no executable TP is authorized."
    first = targets[0]
    return f"Liquidity draw comes from `{first.get('timeframe')}` {first.get('reason')} at `{first.get('price')}`; it is not a TP unless TRADE_PLAN_READY."


def _rr_status(decision: Mapping[str, Any]) -> str:
    rr = decision.get("rr_validation") or {}
    return f"RR status is `{rr.get('status')}` with minimum `{rr.get('minimum_rr', 3.0)}`."


def _final_state(decision: Mapping[str, Any]) -> str:
    if decision.get("trade_plan_state") == "TRADE_PLAN_READY":
        return "Trade plan is ready according to the final narrative authority."
    return "Final state is observe-only: no entry, stop loss, take-profit, risk, leverage, partial close, breakeven, or trailing decision is authorized."


def _contains_forbidden_language(claims: list[Mapping[str, Any]]) -> bool:
    haystack = " ".join(str(claim.get("claim", "")).lower() for claim in claims)
    return any(term in haystack for term in FORBIDDEN_LIVE_ENTRY_WORDS)
