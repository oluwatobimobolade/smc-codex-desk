from __future__ import annotations

from typing import Any


def build_colleague_thesis(
    *,
    symbol: str,
    run_id: str,
    decision_candle_open: str,
    decision_available_at: str,
    mtf_snapshot: dict[str, Any],
    perception_by_tf: dict[str, dict[str, Any]],
    scenario_tree: dict[str, Any],
    decision: dict[str, Any],
    legacy_analysis: dict[str, Any] | None,
    alignment_report: dict[str, Any] | None = None,
    mtf_graph: dict[str, Any] | None = None,
) -> str:
    plan = (legacy_analysis or {}).get("trade_plan", {})
    legacy_enabled = legacy_analysis is not None
    legacy_verdict = f"{plan.get('verdict')} / {plan.get('setup_grade')}" if legacy_enabled else "disabled"
    legacy_direction = str(plan.get("direction")) if legacy_enabled else "disabled"
    alignment_report = alignment_report or {}
    mtf_graph = mtf_graph or {}
    story = mtf_graph.get("market_story", {})
    blockers = story.get("execution_blockers", [])

    lines = [
        f"# {symbol} Market Colleague Thesis",
        "",
        f"Run: `{run_id}`",
        f"Decision candle open: `{decision_candle_open}`",
        f"Decision available at: `{decision_available_at}`",
        "",
        "## Authority",
        "",
        "- PerceptionEngineV2 is the primary perception source for this package.",
        "- Legacy engine output is comparison evidence only when explicitly enabled.",
        "- TradingView/WebBridge evidence can verify visual alignment, not override OHLCV.",
        "- Paper and live execution are disabled.",
        "- Forecast probabilities are not modelled in this slice.",
        "",
        "## Current State",
        "",
        f"- Decision action: `{decision['action']}`",
        f"- MTF execution consensus: `{mtf_snapshot.get('execution_consensus')}`",
        f"- Legacy comparison verdict: `{legacy_verdict}`",
        f"- Legacy comparison direction: `{legacy_direction}`",
        f"- Capital risk: `{decision['capital_risk']}%`",
        f"- TradingView alignment: `{alignment_report.get('status', 'NOT_ATTACHED')}`",
        "",
        "## Perception Snapshot Counts",
        "",
    ]
    for tf in ("1d", "4h", "1h", "15m"):
        payload = perception_by_tf.get(tf, {})
        swings = sum(len(items) for items in payload.get("swings", {}).values())
        lines.append(
            f"- {tf}: swings {swings}, structure breaks {len(payload.get('structure_breaks', []))}, "
            f"FVGs {len(payload.get('fvgs', []))}"
        )

    scenario = scenario_tree.get("scenarios", [{}])[0]
    lines.extend(
        [
            "",
            "## Scenario",
            "",
            f"- Direction: `{scenario.get('direction')}`",
            f"- Status: `{scenario.get('status')}`",
            f"- Setup stage: `{scenario.get('setup_stage')}`",
            f"- Action state: `{scenario.get('current_action_state')}`",
            f"- Next best action: `{scenario.get('next_best_action')}`",
            f"- Probability status: `{scenario.get('probability_status')}`",
            "",
            "## Execution Blockers",
            "",
        ]
    )
    if blockers:
        lines.extend(f"- {item.get('label')} (`{item.get('condition')}`)" for item in blockers)
    else:
        lines.append("- No explicit current-graph blocker was recorded; execution still remains disabled until validation.")

    selected_poi = story.get("poi_context", {}).get("selected_htf_poi")
    lines.extend(
        [
            "",
            "## MTF Story",
            "",
            f"- HTF alignment: `{story.get('htf_alignment', {}).get('execution_consensus', mtf_snapshot.get('execution_consensus'))}`",
            f"- Selected HTF POI: `{selected_poi if selected_poi else 'none'}`",
            f"- Graph nodes/edges: `{len(mtf_graph.get('nodes', []))}` / `{len(mtf_graph.get('edges', []))}`",
            "",
            "## TradingView Alignment",
            "",
            f"- Status: `{alignment_report.get('status', 'NOT_ATTACHED')}`",
            f"- Summary: {alignment_report.get('summary', 'No TradingView/WebBridge alignment report was produced.')}",
        ]
    )
    failures = alignment_report.get("blocking_failures") or []
    if failures:
        lines.append("- Blocking failures:")
        lines.extend(
            f"  - {item.get('name')}: expected `{item.get('expected')}`, observed `{item.get('observed')}`"
            for item in failures[:6]
        )

    lines.extend(
        [
            "",
            "## Legacy Comparison Thesis",
            "",
            str(plan.get("thesis") if legacy_enabled else "Legacy comparison disabled for this run."),
            "",
            "## Missing For Full Colleague",
            "",
            "- Human/adjudicated review of PerceptionEngineV2 objects.",
            "- Full semantic support for OB, inducement, breakers, and richer liquidity maps.",
            "- Scenario probabilities from validated outcome research.",
            "- Comparable historical case retrieval.",
        ]
    )
    return "\n".join(lines) + "\n"
