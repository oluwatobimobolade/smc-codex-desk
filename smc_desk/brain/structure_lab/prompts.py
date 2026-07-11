"""Separate, hashable prompts for each AI structure-lab role."""
from __future__ import annotations

import json
from typing import Any, Mapping

from smc_desk.brain.structure_lab.schemas import ROLE_SCHEMAS
from smc_desk.brain.structure_reasoning_roles import load_structure_reasoning_contract
from smc_desk.data.hashing import object_sha256, sha256_text


ROLE_INSTRUCTIONS = {
    "blind_visual_structure_reader": "Read only clean chart evidence. Describe visible candidates and uncertainty. You have no detector labels and must not call a trade.",
    "deterministic_candidate_reconciler": "Map visual observations to certified evidence IDs. Reject unsupported candidates. Never move a time or price coordinate.",
    "causal_episode_constructor": "Build the parent/child structure story from reconciled evidence. Separate external continuation, internal pullback, transition, range, and uncertainty. Preserve alternatives.",
    "adversarial_structure_critic": "Try to falsify the causal episode against formal-graph invariants and evidence. You may pass, request revision, or downgrade. You may never promote.",
    "annotation_planner": "Choose the few semantic objects a professional SMC trader should see. Select evidence IDs only; the deterministic resolver owns geometry. No trade box.",
    "visual_annotation_critic": "Audit the rendered/declared annotation for clutter, locality, readability, and graph agreement. You may request cleanup or downgrade, never promote.",
}

# WP-0044 stabilization: payload compaction for the structure-lab role prompts.
# Without it, a 4-year BTC case inlines ~9 MB of detector candidates per role,
# which dilutes attention and exceeds practical model context budgets.
CANDIDATE_PER_BUCKET_LIMIT = 80

# Fields a reconciler/planner actually needs to identify a candidate and decide
# whether to reference it. Lifecycle event logs, raw nested evidence blobs,
# candle-ID lists, and detector-internal metadata are dropped -- the certified
# evidence resolver owns geometry and lifecycle.
CANDIDATE_FIELDS: tuple[str, ...] = (
    "object_id",
    "liquidity_id",
    "poi_id",
    "timeframe",
    "direction",
    "break_type",
    "object_type",
    "kind",
    "scale",
    "confidence",
    "confirmation_status",
    "activity_status",
    "mitigation_status",
    "is_wick_only_probe",
    "is_unconfirmed_probe",
    "price",
    "price_low",
    "price_high",
    "broken_price",
    "candidate_at",
    "confirmed_at",
    "pivot_time",
    "candidate_role",
    "truth_status",
    "structure_scope",
)


def _recency_timestamp(candidate: dict[str, Any]) -> str:
    for key in ("confirmed_at", "candidate_at", "pivot_time", "current_as_of", "last_updated_at"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _slim_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields a reconciler/planner needs to reference a candidate."""
    return {key: candidate[key] for key in CANDIDATE_FIELDS if key in candidate}


def compact_candidate_objects(
    candidates: Any,
    *,
    per_bucket_limit: int = CANDIDATE_PER_BUCKET_LIMIT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cap recent candidates per (timeframe, bucket) and slim each item.

    Returns (compacted_candidates, summary) where the summary is transparent
    about what was dropped so nothing is silently truncated.
    """
    summary: dict[str, Any] = {
        "schema": "candidate_compaction_summary_v1",
        "per_bucket_limit": per_bucket_limit,
        "kept_fields": list(CANDIDATE_FIELDS),
        "totals": {
            "candidates_before": 0,
            "candidates_after": 0,
            "buckets_processed": 0,
        },
        "per_bucket": [],
    }
    if not isinstance(candidates, Mapping):
        return candidates, summary
    compacted: dict[str, Any] = {}
    for timeframe, buckets in candidates.items():
        if not isinstance(buckets, Mapping):
            compacted[timeframe] = buckets
            continue
        new_buckets: dict[str, Any] = {}
        for bucket, items in buckets.items():
            summary["totals"]["buckets_processed"] += 1
            if not isinstance(items, list):
                new_buckets[bucket] = items
                continue
            summary["totals"]["candidates_before"] += len(items)
            sortable = [item for item in items if isinstance(item, Mapping)]
            sortable.sort(key=_recency_timestamp, reverse=True)
            kept = sortable[:per_bucket_limit]
            dropped = len(sortable) - len(kept)
            new_buckets[bucket] = [_slim_candidate(item) for item in kept]
            summary["totals"]["candidates_after"] += len(kept)
            summary["per_bucket"].append(
                {
                    "timeframe": timeframe,
                    "bucket": bucket,
                    "before": len(items),
                    "after": len(kept),
                    "dropped": dropped,
                }
            )
        compacted[timeframe] = new_buckets
    return compacted, summary


def compact_role_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compact a role payload in place; return the new payload and summaries."""
    if not isinstance(payload, Mapping) or "candidate_objects" not in payload:
        return payload, []
    candidates = payload.get("candidate_objects")
    compacted, summary = compact_candidate_objects(candidates)
    new_payload = dict(payload)
    new_payload["candidate_objects"] = compacted
    summaries = [summary]
    return new_payload, summaries


def build_role_prompt(
    role: str,
    payload: dict[str, Any],
    *,
    candidate_payload_design: str | None = None,
) -> dict[str, Any]:
    """Build a role prompt.

    ``candidate_payload_design`` selects the candidate-objects payload strategy:
    None / ``"flat"`` keep the legacy recency cap; ``"anchor_tools"`` uses the
    anchor-preserving retriever with the retrieval-tools surface (programme
    §4.6 default). Other designs (full, anchor) are available via
    ``smc_desk.brain.structure_lab.ab_designs.build_candidate_payload`` for the
    step-15 A/B comparison.
    """
    if role not in ROLE_SCHEMAS:
        raise ValueError(f"Unknown structure-lab role: {role}")
    contract = load_structure_reasoning_contract()
    schema = ROLE_SCHEMAS[role].model_json_schema()
    if candidate_payload_design in {"full", "flat", "anchor", "anchor_tools"}:
        # Programme §4.6 anchor-preserving retrieval path. The case is the
        # payload itself (it carries candidate_objects + formal_structure_graph
        # + the anchor source fields the retriever reads).
        from smc_desk.brain.structure_lab.ab_designs import build_candidate_payload
        built = build_candidate_payload(payload, design=candidate_payload_design)
        compacted_payload = dict(payload)
        compacted_payload["candidate_objects"] = built["candidate_objects"]
        summaries = [built["stats"]]
    else:
        compacted_payload, summaries = compact_role_payload(payload)
    prompt = "\n\n".join(
        [
            "You are one governed role inside an AI-first SMC structure laboratory.",
            f"ROLE: {role}",
            ROLE_INSTRUCTIONS[role],
            "GLOBAL PROHIBITIONS:\n- " + "\n- ".join(contract["global_ai_prohibitions"]),
            "Return one strict JSON object matching this schema:\n" + json.dumps(schema, sort_keys=True),
            "ROLE INPUT:\n" + json.dumps(compacted_payload, sort_keys=True, default=str),
        ]
    )
    return {
        "schema": "structure_role_prompt_v1",
        "role": role,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "input_sha256": object_sha256(compacted_payload),
        "output_schema_sha256": object_sha256(schema),
        "contract_sha256": contract["contract_file_sha256"],
        "compaction_summaries": summaries,
    }
