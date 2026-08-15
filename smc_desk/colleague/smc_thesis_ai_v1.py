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
    narrative = _narrative_context(evidence_pack or {})
    claims = [_claim(claim_id, official, evidence_pack or {}, narrative) for claim_id in THESIS_SEQUENCE]
    payload = {
        # Hierarchical market read from the formal graph. Present alongside the
        # decision claims so a reader sees the story the timeframes tell, not
        # just whether they happened to agree. Observe-only: it cannot change
        # validation status, trade-box permission, or official state.
        "market_narrative": narrative,
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
    narrative = payload.get("market_narrative")
    if isinstance(narrative, Mapping) and narrative.get("state"):
        lines.append("## Market Narrative")
        lines.append("")
        lines.append(f"State: `{narrative.get('state')}`")
        context_tf = narrative.get("context_timeframe")
        if context_tf:
            lines.append(f"Context: **{context_tf} {narrative.get('context_bias')}**")
        if narrative.get("retracing_timeframes"):
            lines.append(f"Retracing inside that context: {', '.join(narrative['retracing_timeframes'])}")
        if narrative.get("confirming_timeframes"):
            lines.append(f"Confirming the context: {', '.join(narrative['confirming_timeframes'])}")
        if narrative.get("invalidating_timeframes"):
            lines.append(f"Challenging the context: {', '.join(narrative['invalidating_timeframes'])}")
        draw = narrative.get("draw") or {}
        if isinstance(draw, Mapping) and draw.get("target_price") is not None:
            lines.append(
                f"Draw on liquidity: **{draw.get('direction')} toward {draw.get('target_price')}** "
                f"({draw.get('target_kind')})"
            )
        if narrative.get("sentence"):
            lines.append("")
            lines.append(str(narrative["sentence"]))
        if narrative.get("expectation"):
            lines.append("")
            lines.append(str(narrative["expectation"]))
        if narrative.get("invalidation_note"):
            lines.append("")
            lines.append(f"*{narrative['invalidation_note']}*")
        lines.append("")
        lines.append("_Observe-only hierarchical read. It carries no signal authority._")
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


def _narrative_context(evidence_pack: Mapping[str, Any]) -> dict[str, Any] | None:
    """Pull the hierarchical read off the formal graph, if the graph carries one."""
    session = evidence_pack.get("session_context")
    certificate = session.get("source_identity_certificate") if isinstance(session, Mapping) else None
    if isinstance(certificate, Mapping) and str(certificate.get("status") or "") in {
        "MISMATCH",
        "MISMATCH_PROXY",
    }:
        failures = list(certificate.get("failures") or [])
        return {
            "state": "SOURCE_IDENTITY_MISMATCH",
            "context_timeframe": None,
            "context_bias": "unresolved",
            "is_coherent": False,
            "confirming_timeframes": [],
            "retracing_timeframes": [],
            "invalidating_timeframes": [],
            "draw": {},
            "sentence": (
                "No requested-market narrative was constructed because the candle source "
                "does not match the requested instrument."
            ),
            "expectation": "Acquire a source-verified candle feed and rerun the full system.",
            "invalidation_note": "",
            "source_identity_status": str(certificate.get("status")),
            "source_identity_failure": (
                failures[0] if failures else "requested/provider instrument identity did not match"
            ),
            "authority": "source_identity_quarantine",
            "signal_allowed": False,
        }
    graph = evidence_pack.get("formal_structure_graph")
    if not isinstance(graph, Mapping):
        return None
    narrative = graph.get("narrative_context")
    if not isinstance(narrative, Mapping):
        return None
    result = dict(narrative)
    causal_graph = evidence_pack.get("formal_causal_episode_graph")
    invariants = causal_graph.get("invariants") if isinstance(causal_graph, Mapping) else None
    contract = causal_graph.get("authority_contract") if isinstance(causal_graph, Mapping) else None
    if (
        isinstance(contract, Mapping)
        and contract.get("enforcement_ready") is True
        and isinstance(invariants, Mapping)
        and invariants.get("status") != "PASS"
    ):
        provisional_bias = str(result.get("context_bias") or "unknown")
        violations = [str(value) for value in invariants.get("violations") or []]
        surviving_structure = _surviving_external_structure(causal_graph)
        surviving_text = "; ".join(
            f"{item['timeframe']} {item['direction']} {item['event_type']} ({item['confirmation_time']})"
            for item in surviving_structure
        )
        result.update(
            {
                "state": "RECONCILIATION_REQUIRED",
                "context_timeframe": None,
                "context_bias": "unresolved",
                "is_coherent": False,
                "confirming_timeframes": [],
                "retracing_timeframes": [],
                "invalidating_timeframes": [],
                "draw": {},
                "sentence": (
                    f"The V1 graph provisionally reads {provisional_bias}, but the stricter causal replay "
                    "does not accept every controlling break. Direction remains unresolved for decision authority."
                    + (f" Surviving V3 external structure: {surviving_text}." if surviving_text else "")
                ),
                "expectation": (
                    "Treat the surviving V3 events as scenario evidence only. A trade requires the current "
                    "higher-timeframe route, causal POI, and lower-timeframe entry sequence to agree."
                ),
                "reconciliation_violations": violations,
                "surviving_external_structure": surviving_structure,
            }
        )
    return result


def _surviving_external_structure(causal_graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    timeframes = causal_graph.get("timeframes")
    if not isinstance(timeframes, Mapping):
        return []
    out: list[dict[str, Any]] = []
    for timeframe in ("1d", "4h", "1h", "15m"):
        node = timeframes.get(timeframe)
        episode = node.get("latest_external_episode") if isinstance(node, Mapping) else None
        if not isinstance(episode, Mapping):
            continue
        direction = str(episode.get("direction") or "unknown")
        event_type = str(episode.get("event_type") or "UNRESOLVED")
        confirmation_time = episode.get("confirmation_time")
        if direction not in {"bullish", "bearish"} or not confirmation_time:
            continue
        out.append(
            {
                "timeframe": timeframe,
                "direction": direction,
                "event_type": event_type,
                "confirmation_time": str(confirmation_time),
                "structure_event_id": episode.get("structure_event_id"),
            }
        )
    return out


def _claim(
    claim_id: str,
    official: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
    narrative: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    title = claim_id.replace("_", " ").title()
    if claim_id == "bias_summary":
        bias = official.get("bias_summary") or {}
        prefix = (
            "Provisional V1 votes: "
            if isinstance(narrative, Mapping) and narrative.get("state") == "RECONCILIATION_REQUIRED"
            else ""
        )
        text = f"{prefix}Daily={bias.get('daily')}; 4H={bias.get('4h')}; 1H={bias.get('1h')}; final bias={bias.get('final_bias')}."
        if prefix:
            text += " Decision-authority bias remains unresolved until the causal replay reconciles."
        # A "mixed" vote describes the tally, not the market. When the graph
        # resolved a coherent hierarchical story, state it -- disagreement
        # between timeframes is what a retracement IS.
        if isinstance(narrative, Mapping) and narrative.get("is_coherent"):
            text += f" Hierarchical read: {narrative.get('sentence')}"
    elif claim_id == "active_range":
        active_range = official.get("active_range") or {}
        if active_range.get("low") is None or active_range.get("high") is None:
            text = (
                "No requested-market active range is authorized. "
                + str((active_range.get("evidence") or ["Acquire valid market evidence and rerun."])[0])
            )
        else:
            text = f"{active_range.get('timeframe')} range {active_range.get('low')} to {active_range.get('high')}; location={active_range.get('price_location')}."
    elif claim_id == "liquidity_story":
        story = official.get("liquidity_story") or {}
        text = str(story.get("narrative") or "No liquidity story supplied.")
        draw = (narrative or {}).get("draw") if isinstance(narrative, Mapping) else None
        if isinstance(draw, Mapping) and draw.get("target_price") is not None:
            text += (
                f" Draw on liquidity: {draw.get('direction')} toward "
                f"{draw.get('target_price')} ({draw.get('target_kind')}). "
                f"{draw.get('rationale')}"
            )
    elif claim_id == "displacement_assessment":
        displacement = official.get("displacement_assessment") or {}
        text = _format_displacement(displacement)
    elif claim_id == "active_poi":
        poi = official.get("active_poi") or {}
        if poi.get("poi_id") or poi.get("price_low") is not None or poi.get("price_high") is not None:
            text = _format_poi(poi)
        else:
            scenario_text = _format_scenario_watch_pois(evidence_pack)
            if scenario_text:
                title = "Scenario Poi Map"
                text = scenario_text
            else:
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


def _format_scenario_watch_pois(evidence_pack: Mapping[str, Any]) -> str | None:
    authority = evidence_pack.get("causal_poi_authority") or {}
    scenarios = authority.get("scenarios") if isinstance(authority, Mapping) else None
    if not isinstance(scenarios, Mapping):
        return None
    causal_graph = evidence_pack.get("formal_causal_episode_graph") or {}
    current_story = causal_graph.get("current_story") if isinstance(causal_graph, Mapping) else None
    route_map = current_story.get("route_map") if isinstance(current_story, Mapping) else None
    disputed_items = route_map.get("disputed_objects") if isinstance(route_map, Mapping) else None
    disputed_by_id = {
        str(item.get("poi_id") or item.get("source_object_id")): item
        for item in disputed_items or []
        if isinstance(item, Mapping)
        and (item.get("poi_id") or item.get("source_object_id"))
        and item.get("display_authority") == "WITHHELD"
    }
    mapped: list[str] = []
    withheld: list[str] = []
    for direction in ("bullish", "bearish"):
        scenario = scenarios.get(direction)
        primary = scenario.get("primary_causal_poi") if isinstance(scenario, Mapping) and scenario.get("status") == "SELECTED" else None
        if not isinstance(primary, Mapping):
            continue
        poi_id = str(primary.get("poi_id") or primary.get("source_object_id") or "")
        dispute = disputed_by_id.get(poi_id)
        if dispute is not None:
            dispute_reason = str(
                dispute.get("reason")
                or "its linked structure event did not survive causal replay"
            ).rstrip(" .")
            withheld.append(
                f"{direction} {primary.get('timeframe')} {primary.get('kind')} "
                f"{primary.get('price_low')}-{primary.get('price_high')} withheld: "
                f"{dispute_reason}"
            )
            continue
        mapped.append(
            f"{direction} scenario: {primary.get('timeframe')} {primary.get('kind')} "
            f"{primary.get('price_low')}-{primary.get('price_high')} "
            f"({primary.get('lineage_role')}, lifecycle={primary.get('freshness')})"
        )
    if not mapped and not withheld:
        return None
    parts: list[str] = []
    if mapped:
        parts.append(
            "; ".join(mapped)
            + ". These are conditional route-map POIs only; they are not an official active POI or trade plan."
        )
    if withheld:
        parts.append("No authority is granted to disputed POIs. " + "; ".join(withheld) + ".")
    return " ".join(parts)
