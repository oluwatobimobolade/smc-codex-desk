"""Export a complete review packet for an external AI agent.

The packet contains everything an external AI agent (Codex, Gemini Antigravity,
ChatGPT, Kimi, etc.) needs to reason as the SMC trader brain:

  - 00_READ_ME_FIRST.md         — packet order and sealed bindings
  - 00_AI_SEAT_PROFILE.md       — exact proposed AI seat profile
  - 00_MARKET_STRUCTURE_CONSTITUTION_V2.yaml — exact doctrine snapshot
  - 00_PERCEPTION_GAUNTLET_PROTOCOL.json — protocol-conformance contract
  - 00_SEMANTIC_METAMORPHIC_EVIDENCE.json — mechanical mirror evidence
  - 00_authority_manifest.json  — authority types, statuses, and hashes
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
    AGENT_PACKET_SCHEMA,
    AGENT_PACKET_FILES,
)
from smc_desk.brain.agent_handoff.ai_seat_contract import (
    AUTHORITY_MANIFEST_PACKET_NAME,
    CONSTITUTION_PACKET_NAME,
    GAUNTLET_PACKET_NAME,
    METAMORPHIC_PACKET_NAME,
    PROFILE_PACKET_NAME,
    build_authority_bundle,
)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _read_instructions(authority_manifest: Mapping[str, Any]) -> str:
    profile = authority_manifest["ai_seat_profile"]
    constitution = authority_manifest["constitution"]
    gauntlet = authority_manifest["gauntlet"]
    return f"""# AI SMC Trader Brain — External Agent Review Packet V2

This is a hash-sealed, observe-only reasoning packet. Read files in this order:

1. `{AUTHORITY_MANIFEST_PACKET_NAME}` — verify authority status and hashes.
2. `{CONSTITUTION_PACKET_NAME}` — semantic doctrine; preserve pending decisions.
3. `{PROFILE_PACKET_NAME}` — the exact AI Seat Profile governing this packet.
4. `{GAUNTLET_PACKET_NAME}` — protocol-conformance tests, never self-scored accuracy.
5. `02_evidence_pack.json` and the clean charts — frozen case evidence.
6. `{METAMORPHIC_PACKET_NAME}` — mechanically mirrored OHLCV for Station 8.
7. `09_expected_output_schema.json` — required response and ten-station exam.

## Sealed authority bindings

- AI Seat Profile SHA-256: `{profile['sha256']}`
- Constitution V2 SHA-256: `{constitution['sha256']}`
- Constitution status: `{constitution['status']}`
- Pending doctrine decisions: `{constitution['pending_count']}`
- Gauntlet protocol SHA-256: `{gauntlet['protocol_sha256']}`

## Non-negotiable response contract

- Return the wrapper schema in `09_expected_output_schema.json`.
- Complete every `exam_transcript` station with concise evidence, not private chain-of-thought.
- A failed, unresolved, missing, ungrounded, or hash-mismatched station forces `REVIEW_REQUIRED` and strips entry/SL/TP/RR/trade annotations.
- Record detector disagreements in `dissent_records`; never silently replace evidence.
- Record doctrine-dependent unresolved claims in `doctrine_pending_claims`.
- Audit `annotation_context_authority` after deciding the active POI. An object
  rejected for active entry may be retained only when it has a prequalified
  requirement ID. Cite it in `context_exception_requests`, request
  `context_only`, and acknowledge that it cannot change bias or grant entry.
- The AI seat, self-exam, and gauntlet have no promotion, signal, paper, live, or execution authority.
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
- Prefer annotation_plan_v2 for professional markup. Every V2 object must be sparse, local, readable, and grounded with evidence_object_ids and exact source geometry. For structure, declare the matching external/internal scope. A path requires a certified active POI; a trade_box requires kind=trade plus validated entry_price, stop_price, and target_prices.
- A contextual exception is visibility-only. It must cite an existing
  `annotation_context_authority.requirements[].requirement_id`, preserve exact
  geometry, use a context display role, set `active_entry_authority=false`, and
  cannot alter the active POI, direction, entry, stop, target, or trade state.

## Parent-child conflict

- If 1d/4h conflicts with 1h/15m: direction=mixed, official_state=THESIS_ONLY or REVIEW_REQUIRED.
- Final thesis must name parent timeframe, child timeframe, both biases, and the pullback/recovery relationship.

## Formal causal structure authority

- Read formal_causal_episode_graph before formal_structure_graph. The causal episode graph is stricter and can only downgrade the older graph.
- The formal_structure_graph remains the deterministic source for parent-child context and active-range anchors where the causal graph does not challenge them.
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
            source_rows = list((evidence_pack.get("ohlcv_windows") or {}).get(tf) or [])
            manifest["timeframes"][tf] = {
                "path": str(path),
                "sha256": _hash_file(path),
                "size_bytes": path.stat().st_size,
                "row_count": len(source_rows),
                "evidence_bound": bool(source_rows),
                "source": "evidence_pack.ohlcv_windows" if source_rows else "provided_chart_path",
                "source_window_sha256": _hash_json(source_rows) if source_rows else None,
            }
    return manifest


def _materialize_packet_charts(
    *,
    symbol: str,
    evidence_pack: Mapping[str, Any],
    provided_chart_paths: Mapping[str, Path],
    output_dir: Path,
) -> dict[str, Path]:
    """Render packet charts from the exact sealed OHLCV windows when present.

    Supplied images remain a compatibility fallback only for synthetic or
    legacy packets that do not carry source rows.
    """
    tf_to_filename = {
        "1d": "04_clean_1d_chart.png",
        "4h": "05_clean_4h_chart.png",
        "1h": "06_clean_1h_chart.png",
        "15m": "07_clean_15m_chart.png",
        "5m": "07b_clean_5m_chart.png",
    }
    bound_paths: dict[str, Path] = {}
    windows = evidence_pack.get("ohlcv_windows") or {}
    for timeframe, filename in tf_to_filename.items():
        destination = output_dir / filename
        rows = list(windows.get(timeframe) or []) if isinstance(windows, Mapping) else []
        if rows:
            import pandas as pd

            from smc_desk.rendering.clean_mtf_chart_pack import render_clean_candle_chart

            frame = pd.DataFrame(rows)
            if "timestamp" not in frame.columns:
                raise ValueError(f"Evidence window {timeframe} has no timestamp column.")
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            render_clean_candle_chart(
                frame,
                destination,
                symbol=symbol,
                timeframe=timeframe,
                max_display_bars=None,
            )
            bound_paths[timeframe] = destination
            continue
        source = provided_chart_paths.get(timeframe)
        if source and source.exists():
            shutil.copy2(source, destination)
            bound_paths[timeframe] = destination
    return bound_paths


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

    authority_bundle = build_authority_bundle(evidence_pack)
    authority_manifest = authority_bundle["authority_manifest"]
    if authority_manifest["status"] != "PASS":
        raise ValueError(
            "Cannot export an AI agent packet with invalid authority bindings: "
            + ", ".join(authority_manifest["violations"])
        )
    (output_dir / PROFILE_PACKET_NAME).write_text(authority_bundle["profile_text"], encoding="utf-8")
    (output_dir / CONSTITUTION_PACKET_NAME).write_bytes(authority_bundle["constitution_bytes"])
    (output_dir / GAUNTLET_PACKET_NAME).write_text(
        json.dumps(authority_bundle["gauntlet_protocol"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / METAMORPHIC_PACKET_NAME).write_text(
        json.dumps(authority_bundle["metamorphic_evidence"], indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output_dir / AUTHORITY_MANIFEST_PACKET_NAME).write_text(
        json.dumps(authority_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "00_READ_ME_FIRST.md").write_text(
        _read_instructions(authority_manifest), encoding="utf-8"
    )
    (output_dir / "01_prompt_bundle.md").write_text(_read_prompt_bundle(), encoding="utf-8")
    (output_dir / "02_evidence_pack.json").write_text(
        json.dumps(evidence_pack, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    packet_chart_paths = _materialize_packet_charts(
        symbol=symbol,
        evidence_pack=evidence_pack,
        provided_chart_paths=chart_paths,
        output_dir=output_dir,
    )
    chart_manifest = _build_chart_manifest(packet_chart_paths, evidence_pack)
    (output_dir / "03_chart_manifest.json").write_text(
        json.dumps(chart_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    candidate_levels = _build_candidate_levels(evidence_pack)
    (output_dir / "08_candidate_levels.json").write_text(
        json.dumps(candidate_levels, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    (output_dir / "10_guardrails.md").write_text(_read_guardrails(), encoding="utf-8")

    evidence_pack_hash = _hash_json(evidence_pack)
    sealed_input_names = [
        filename
        for filename in AGENT_PACKET_FILES
        if filename not in {"09_expected_output_schema.json", "run_manifest.json"}
        and (output_dir / filename).exists()
    ]
    optional_5m = output_dir / "07b_clean_5m_chart.png"
    if optional_5m.exists():
        sealed_input_names.append(optional_5m.name)
    input_file_hashes = {
        filename: _hash_file(output_dir / filename)
        for filename in sorted(set(sealed_input_names))
    }
    sealed_input_hash = _hash_json(input_file_hashes)

    from smc_desk.brain.agent_handoff.agent_schemas import make_agent_response_template

    (output_dir / "09_expected_output_schema.json").write_text(
        json.dumps(
            make_agent_response_template(
                authority_manifest=authority_manifest,
                packet_hash=sealed_input_hash,
                decision_time=decision_time,
            ),
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    actual_files = list(AGENT_PACKET_FILES)
    if optional_5m.exists():
        actual_files.append(optional_5m.name)
    file_hashes: dict[str, str] = {}
    for filename in actual_files:
        path = output_dir / filename
        if path.exists() and filename != "run_manifest.json":
            file_hashes[filename] = _hash_file(path)

    manifest = {
        "schema": AGENT_PACKET_SCHEMA,
        "packet_type": AGENT_PACKET_SCHEMA,
        "symbol": symbol,
        "decision_time": decision_time,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": actual_files,
        "file_hashes": file_hashes,
        "input_file_hashes": input_file_hashes,
        "sealed_input_hash": sealed_input_hash,
        "evidence_pack_hash": evidence_pack_hash,
        "authority_manifest_hash": _hash_file(output_dir / AUTHORITY_MANIFEST_PACKET_NAME),
        "ai_seat_profile_hash": authority_manifest["ai_seat_profile"]["sha256"],
        "constitution_hash": authority_manifest["constitution"]["sha256"],
        "gauntlet_protocol_hash": authority_manifest["gauntlet"]["protocol_sha256"],
        "chart_count": len(chart_manifest.get("timeframes", {})),
        "timeframes": list(chart_manifest.get("timeframes", {}).keys()),
        "authority_contract": {
            "execution": "disabled",
            "capital_risk": 0,
            "observe_only": True,
            "self_certification_allowed": False,
            "independent_exam_validation_required": True,
        },
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return manifest
