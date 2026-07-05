"""Export a complete review packet for an external AI agent.

The packet contains everything an external AI agent (Codex, Gemini Antigravity,
ChatGPT, Kimi, etc.) needs to reason as the SMC trader brain:

  - 00_READ_ME_FIRST.md         — agent instructions
  - 01_prompt_bundle.md         — full prompt system
  - 02_evidence_pack.json       — structured evidence
  - 03_chart_manifest.json      — chart file manifest with hashes
  - 04-07_clean_*_chart.png     — clean candle charts per timeframe
  - 08_candidate_levels.json    — detector candidate levels
  - 09_expected_output_schema.json — response schema
  - 10_guardrails.md            — non-negotiables and rules
  - run_manifest.json           — packet metadata and hashes
"""
from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smc_desk.brain.agent_handoff.agent_schemas import (
    AGENT_PACKET_FILES,
    AgentPacketSchema,
)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _read_instructions() -> str:
    return """# AI SMC Trader Brain — External Agent Review Packet

You are being asked to act as the **AI SMC Trader Brain** for this analysis run.

The system has already done the following:

1. Fetched live OHLCV data (Binance USD-M, Yahoo FX, or Yahoo XAU).
2. Built clean candle charts for each timeframe.
3. Ran the detector pipeline to extract structure breaks, sweeps, order blocks, FVGs, and liquidity levels.
4. Built an evidence pack with active range authority, parent-child context, and the formal structure graph.
5. Generated this packet for your review.

## Your job

Think top-down like a disciplined intraday SMC trader:

- Use **Daily** and **4H** for HTF bias and context.
- Use **1H** for intermediate structure and displacement quality.
- Use **15M** for entry confirmation and POI reaction.
- **5M** is optional refinement only. **1M is forbidden.**
- Do not force trades. If the evidence does not support a trade-ready setup, return WATCH_ONLY, THESIS_ONLY, or REVIEW_REQUIRED.
- Return **strict JSON only** in `official_decision_candidate.json`. Use the schema in `09_expected_output_schema.json`.
- **Semantic anchors first, exact prices second.** Name the structural reason (e.g. "1h supply origin after 4h BSL sweep") before giving exact prices.
- Do not invent levels. If a level is not in the evidence pack or chart, do not include it.
- If you need more context, write `REQUEST_MORE_CONTEXT` in `requested_more_context.json`.

## Reasoning order (must follow)

1. daily_context
2. 4h_context
3. 1h_context
4. active_range
5. premium_discount
6. obvious_liquidity
7. swept_liquidity
8. displacement_quality
9. active_poi
10. entry_model
11. entry_readiness
12. structural_invalidation
13. model_completion_liquidity_target
14. rr_minimum_three
15. final_state

## Guardrails (non-negotiable)

- **Minimum RR = 3.0**. If RR < 3.0, do not return TRADE_PLAN_READY.
- **No 1m entry.** 1m is forbidden.
- **Watch states must not have entry/SL/TP/RR or trade box.**
- **Trade-ready states must have grounded entry, stop, and target with semantic anchors.**
- **Parent-child conflict forces direction=mixed and state=THESIS_ONLY or REVIEW_REQUIRED.**
- **Wick probes are not confirmed breaks.**
- **Active range must come from protected swing structure, not OHLCV summary extremes.**
- **Do not claim live/paper execution, capital risk, or leverage.**

## What to write back

1. `official_decision_candidate.json` — strict JSON matching `09_expected_output_schema.json`.
2. `agent_reasoning_summary.md` — short markdown summary of your reasoning.
3. `annotation_plan.json` — chart labels and levels for rendering.
4. `requested_more_context.json` (optional) — if you need more data.

The system will then validate your response, ground your levels in OHLCV, render the chart, and produce the final thesis.
"""


def _read_prompt_bundle() -> str:
    try:
        from smc_desk.brain.prompt_system import build_prompt_registry_manifest
        manifest = build_prompt_registry_manifest(include_text=True)
        return json.dumps(manifest, indent=2, sort_keys=True, default=str)
    except Exception as exc:
        return f"# Prompt Bundle (unavailable: {exc})"


def _read_guardrails() -> str:
    return """# Guardrails — Non-Negotiable Rules

## Provider mode

This packet is for an **EXTERNAL_AI_AGENT**. The system does not call an LLM API directly. The external agent reviews this packet and returns a decision JSON.

## Trade readiness

- TRADE_PLAN_READY requires: validated entry, structural stop, model-completion target, RR >= 3.0.
- TRADE_PLAN_READY requires: clean/strong displacement, structure_broken=true, displacement evidence_object_ids.
- TRADE_PLAN_READY requires: trade_plan_chart template, show_trade_box=true.

## Watch states

- WATCH_ONLY, THESIS_ONLY, WAIT_FOR_*, POI_TOUCHED_*, MISSED_TRADE_NO_CHASE, VALID_DIRECTION_BAD_RR_WAIT_FOR_BETTER_ENTRY, INDUCEMENT_RISK, INVALIDATED_REMAP, MOVE_STARTED_NOT_CHASEABLE, NO_TRADE must NOT have entry/SL/TP/RR or trade box.
- Use chart_template: context_chart, watch_chart, or review_chart.

## Parent-child conflict

- If 1d/4h conflicts with 1h/15m: direction=mixed, official_state=THESIS_ONLY or REVIEW_REQUIRED.
- Final thesis must name parent timeframe, child timeframe, both biases, and the pullback/recovery relationship.

## Formal structure graph

- The formal_structure_graph in the evidence pack is the single authoritative source for parent-child context, active range authority, and invariant status.
- Graph invariants: internal_child_cannot_flip_parent, child_body_close_required_for_parent_break, wick_probes_are_not_breaks, active_range_from_swing_structure, ohcl_summary_not_range_source, parent_child_conflict_blocks_trade_ready.
- If graph invariants are not PASS, the decision must be REVIEW_REQUIRED.
- If graph says trade_promotion_blocked, TRADE_PLAN_READY is forbidden.

## Semantic anchors

- entry_anchor: structural reason for the entry price (e.g. "1h_supply_origin", "4h_demand_origin")
- stop_anchor: structural reason for the stop (e.g. "1h_supply_origin_high", "4h_range_high")
- target_anchor: structural reason for the target (e.g. "4h_ssl", "1d_protected_low")
- invalidation_anchor: structural reason for invalidation
- The system will map these to exact prices using the evidence pack.

## Forbidden

- No 1m entry timeframe.
- No live execution, paper execution, or capital risk claims.
- No invented levels not in the evidence pack.
- No OHLCV summary highs/lows as the active dealing range.
- No TRADE_PLAN_READY without RR >= 3.0.
"""


def _build_chart_manifest(timeframe_dfs: Mapping[str, Path], evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    manifest = {"schema": "ai_smc_chart_manifest_v1", "timeframes": {}}
    for tf, path in timeframe_dfs.items():
        if path and path.exists():
            manifest["timeframes"][tf] = {
                "path": str(path),
                "sha256": _hash_file(path),
                "size_bytes": path.stat().st_size,
                "row_count": len(evidence_pack.get("ohlcv_windows", {}).get(tf, [])),
            }
    return manifest


def _build_candidate_levels(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    """Extract candidate levels for the agent to reference."""
    candidates = evidence_pack.get("detector_candidates", {})
    levels: dict[str, list[dict[str, Any]]] = {}
    for tf, payload in candidates.items():
        if not isinstance(payload, Mapping):
            continue
        levels[tf] = []
        for ob in payload.get("order_blocks", []) or []:
            if isinstance(ob, Mapping):
                levels[tf].append({
                    "object_id": ob.get("object_id"),
                    "type": "order_block",
                    "direction": ob.get("direction"),
                    "price_low": ob.get("price_low"),
                    "price_high": ob.get("price_high"),
                })
        for liq in payload.get("liquidity_levels", []) or []:
            if isinstance(liq, Mapping):
                levels[tf].append({
                    "object_id": liq.get("object_id"),
                    "type": "liquidity_level",
                    "side": liq.get("side"),
                    "price": liq.get("price"),
                })
    return {"schema": "ai_smc_candidate_levels_v1", "by_timeframe": levels}


def export_agent_packet(
    *,
    symbol: str,
    evidence_pack: Mapping[str, Any],
    chart_paths: Mapping[str, Path],
    output_dir: Path,
    decision_time: str | None = None,
) -> dict[str, Any]:
    """Export a complete review packet for an external AI agent.

    Returns the run_manifest with all file hashes and metadata.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_time = decision_time or datetime.now(timezone.utc).isoformat()

    (output_dir / "00_READ_ME_FIRST.md").write_text(_read_instructions(), encoding="utf-8")
    (output_dir / "01_prompt_bundle.md").write_text(_read_prompt_bundle(), encoding="utf-8")
    (output_dir / "02_evidence_pack.json").write_text(
        json.dumps(evidence_pack, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    chart_manifest = _build_chart_manifest(chart_paths, evidence_pack)
    (output_dir / "03_chart_manifest.json").write_text(
        json.dumps(chart_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    tf_to_filename = {"1d": "04_clean_1d_chart.png", "4h": "05_clean_4h_chart.png", "1h": "06_clean_1h_chart.png", "15m": "07_clean_15m_chart.png", "5m": "07b_clean_5m_chart.png"}
    for tf, filename in tf_to_filename.items():
        src = chart_paths.get(tf)
        if src and src.exists():
            shutil.copy2(src, output_dir / filename)

    candidate_levels = _build_candidate_levels(evidence_pack)
    (output_dir / "08_candidate_levels.json").write_text(
        json.dumps(candidate_levels, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    from smc_desk.brain.agent_handoff.agent_schemas import make_agent_response_template
    (output_dir / "09_expected_output_schema.json").write_text(
        json.dumps(make_agent_response_template(), indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    (output_dir / "10_guardrails.md").write_text(_read_guardrails(), encoding="utf-8")

    packet_hash = _hash_json(evidence_pack)
    file_hashes: dict[str, str] = {}
    for filename in AGENT_PACKET_FILES:
        path = output_dir / filename
        if path.exists():
            file_hashes[filename] = _hash_file(path)

    manifest = {
        "schema": "ai_smc_agent_packet_v1",
        "packet_type": AgentPacketSchema,
        "symbol": symbol,
        "decision_time": decision_time,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": AGENT_PACKET_FILES,
        "file_hashes": file_hashes,
        "evidence_pack_hash": packet_hash,
        "chart_count": len(chart_manifest.get("timeframes", {})),
        "timeframes": list(chart_manifest.get("timeframes", {}).keys()),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return manifest
