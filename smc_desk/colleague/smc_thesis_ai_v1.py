"""AI SMC thesis writer.

This writer consumes only the validated AI SMC decision boundary. It does not
promote raw detector candidates or unvalidated model claims.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smc_desk.brain.ai_smc_consistency_validator import ValidationResult


THESIS_SEQUENCE = [
    "bias_summary",
    "active_range",
    "liquidity_story",
    "displacement_assessment",
    "active_poi",
    "entry_readiness",
    "structural_invalidation",
    "target_plan",
    "rr_status",
    "final_state",
]


def build_smc_thesis_ai_v1(
    *,
    validation_result: ValidationResult,
    evidence_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    official = validation_result.official_decision
    claims = [_claim(claim_id, official) for claim_id in THESIS_SEQUENCE]
    payload = {
        "schema": "smc_thesis_ai_v1",
        "source": "ValidatedAISMCDecision" if validation_result.status == "VALIDATED" else "ReviewRequiredAISMCDecision",
        "validation_status": validation_result.status,
        "smc_model_validity": validation_result.smc_model_validity,
        "trade_plan_validity": validation_result.trade_plan_validity,
        "validation_message": official.get("validation_message"),
        "symbol": official.get("symbol"),
        "official_state": official.get("official_state"),
        "setup_model": official.get("setup_model"),
        "direction": official.get("direction"),
        "chart_template": (official.get("annotation_plan") or {}).get("chart_template"),
        "show_trade_box": bool((official.get("annotation_plan") or {}).get("show_trade_box")),
        "claim_sequence": THESIS_SEQUENCE,
        "claims": claims,
        "final_thesis": official.get("final_thesis"),
        "validation_issues": [issue.model_dump(mode="json") for issue in validation_result.issues],
        "evidence_pack_hash": ((evidence_pack or {}).get("provenance") or {}).get("pack_hash"),
    }
    assert_smc_thesis_ai_v1_contract(payload)
    return payload


def render_smc_thesis_ai_v1_markdown(payload: Mapping[str, Any]) -> str:
    lines = [f"# {payload.get('symbol')} AI SMC Thesis V1", ""]
    lines.append(f"Source: `{payload.get('source')}`")
    lines.append(f"Validation: `{payload.get('validation_status')}`")
    lines.append(f"SMC Model Validity: `{payload.get('smc_model_validity')}`")
    lines.append(f"Trade Plan Validity: `{payload.get('trade_plan_validity')}`")
    if payload.get("validation_message"):
        lines.append(f"Validation Message: *{payload.get('validation_message')}*")
    lines.append(f"Official state: `{payload.get('official_state')}`")
    lines.append(f"Setup model: `{payload.get('setup_model')}`")
    lines.append(f"Trade box: `{payload.get('show_trade_box')}`")
    if payload.get("evidence_pack_hash"):
        lines.append(f"Evidence pack hash: `{payload.get('evidence_pack_hash')}`")
    lines.append("")
    for index, claim in enumerate(payload.get("claims", []) or [], start=1):
        lines.append(f"## {index}. {claim['title']}")
        lines.append("")
        lines.append(str(claim["claim"]))
        lines.append("")
    issues = payload.get("validation_issues") or []
    if issues:
        lines.append("## Validation Issues")
        lines.append("")
        for issue in issues:
            lines.append(f"- `{issue.get('code')}`: {issue.get('message')}")
        lines.append("")
    lines.append("## Final Thesis")
    lines.append("")
    lines.append(str(payload.get("final_thesis") or "No final thesis supplied."))
    return "\n".join(lines)


def assert_smc_thesis_ai_v1_contract(payload: Mapping[str, Any]) -> None:
    if payload.get("claim_sequence") != THESIS_SEQUENCE:
        raise AssertionError("AI SMC thesis does not follow the required sequence.")
    if payload.get("validation_status") != "VALIDATED" and payload.get("show_trade_box"):
        raise AssertionError("Review-required thesis cannot show a trade box.")
    if payload.get("chart_template") != "trade_plan_chart" and payload.get("show_trade_box"):
        raise AssertionError("Only trade_plan_chart may show a trade box.")


def _claim(claim_id: str, official: Mapping[str, Any]) -> dict[str, Any]:
    title = claim_id.replace("_", " ").title()
    if claim_id == "bias_summary":
        bias = official.get("bias_summary") or {}
        text = f"Daily={bias.get('daily')}; 4H={bias.get('4h')}; 1H={bias.get('1h')}; final bias={bias.get('final_bias')}."
    elif claim_id == "active_range":
        active_range = official.get("active_range") or {}
        text = f"{active_range.get('timeframe')} range {active_range.get('low')} to {active_range.get('high')}; location={active_range.get('price_location')}."
    elif claim_id == "liquidity_story":
        story = official.get("liquidity_story") or {}
        text = str(story.get("narrative") or "No liquidity story supplied.")
    elif claim_id == "displacement_assessment":
        displacement = official.get("displacement_assessment") or {}
        text = _format_displacement(displacement)
    elif claim_id == "active_poi":
        poi = official.get("active_poi") or {}
        text = _format_poi(poi)
    elif claim_id == "entry_readiness":
        entry = official.get("entry_plan") or {}
        text = f"entry_ready={entry.get('entry_ready')}; timeframe={entry.get('entry_timeframe')}; {entry.get('summary')}"
    elif claim_id == "structural_invalidation":
        invalidation = official.get("invalidation") or {}
        stop = official.get("stop_loss_plan") or {}
        text = f"invalidation={invalidation.get('invalidation_price')}; stop={stop.get('stop_price')}; condition={invalidation.get('condition')}"
    elif claim_id == "target_plan":
        target = official.get("target_plan") or {}
        text = str(target.get("summary") or "No target authorized.")
    elif claim_id == "rr_status":
        rr = official.get("rr_status") or {}
        text = f"RR={rr.get('rr')}; pass_rr={rr.get('pass_rr')}; minimum={rr.get('minimum_rr')}. {rr.get('notes')}"
    else:
        text = f"Final state is {official.get('official_state')}."
    return {"claim_id": claim_id, "title": title, "claim": text, "source": "official_decision"}


def _format_displacement(displacement: Mapping[str, Any]) -> str:
    direction = str(displacement.get("direction") or "none")
    quality = str(displacement.get("quality") or "none")
    summary = str(displacement.get("summary") or "").strip()
    if direction == "none" and quality == "none":
        return summary or "No displacement confirmed."
    return f"{direction} {quality} displacement; structure_broken={displacement.get('structure_broken', False)}. {summary}".strip()


def _format_poi(poi: Mapping[str, Any]) -> str:
    if not poi.get("poi_id") and poi.get("price_low") is None and poi.get("price_high") is None:
        return str(poi.get("summary") or "No active POI at current price.")
    timeframe = str(poi.get("timeframe") or "").strip()
    kind = str(poi.get("kind") or "POI").strip()
    low = poi.get("price_low", "?")
    high = poi.get("price_high", "?")
    prefix = f"{timeframe} {kind}".strip()
    return f"{prefix} {low}-{high}: {poi.get('summary') or ''}".strip()
