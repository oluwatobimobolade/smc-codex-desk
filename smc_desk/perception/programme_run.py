"""Honest vertical runner for the experimental SMC perception programme.

This module is deliberately explicit about what actually ran. A supplied
fixture is useful for validator replay, but it is not described as an AI run.
When a provider is supplied, the six governed structure roles execute in
sequence and their evidence-grounded causal episode becomes the interpretation
that deterministic validators assess. Optional OHLCV frames build the real
multi-timeframe candidate atlas under the decision-time cutoff.

The Market Structure Constitution remains PROPOSED, so this runner cannot
create authoritative perception or a signal even when every implementation
check passes.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, TYPE_CHECKING

from smc_desk.brain.structure_lab.ab_designs import build_candidate_payload
from smc_desk.brain.structure_lab.runtime import StructureRoleProvider, run_structure_lab
from smc_desk.data.hashing import file_sha256, object_sha256
from smc_desk.perception.candidates import atlas as atlas_mod
from smc_desk.structure.doctrine import is_authoritative, unresolved_contested_decisions
from smc_desk.validation import certify_interpretation

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class PerceptionRunEnvelope:
    schema: str = "perception_run_envelope_v2"
    doctrine_authoritative: bool = False
    atlas_built: bool = False
    atlas_sha256: str = ""
    atlas_candidate_counts: dict[str, int] = field(default_factory=dict)
    context_sha256: str = ""
    candidate_payload_design: str = "anchor"
    retrieval_tools_advertised: bool = False
    retrieval_tools_executed: bool = False
    role_run_executed: bool = False
    role_run_status: str = "NOT_RUN"
    role_run_manifest_sha256: str = ""
    interpretation_source: str = "NONE"
    annotation_render_status: str = "NOT_RENDERED"
    abstention_reason: str = ""
    certification: dict[str, Any] = field(default_factory=dict)
    contested_decisions_unresolved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_perception_programme(
    *,
    case: Mapping[str, Any],
    decision_time: str,
    per_timeframe_cutoff: Mapping[str, str] | None = None,
    timeframe_dfs: Mapping[str, "pd.DataFrame"] | None = None,
    atlas_configs: Mapping[str, atlas_mod.AtlasConfig] | None = None,
    candidate_pool: list[Mapping[str, Any]] | None = None,
    role_provider: StructureRoleProvider | None = None,
    role_output_dir: str | Path | None = None,
    annotation_renderer: Callable[[Mapping[str, Any], Mapping[str, Any], Path], Mapping[str, Any]] | None = None,
    interpretation: Mapping[str, Any] | None = None,
    candidate_overrides: set[str] | None = None,
    fill_budget: int = 600,
    atlas_config: atlas_mod.AtlasConfig | None = None,
) -> PerceptionRunEnvelope:
    """Execute the available vertical slice and return a provenance envelope.

    ``interpretation`` is accepted only as an explicitly labelled replay
    fixture. A real governed role run requires ``role_provider`` and
    ``role_output_dir``. Supplying both an interpretation and a provider is
    rejected because the provenance would be ambiguous.
    """
    if not decision_time:
        raise ValueError("run_perception_programme requires decision_time")
    if role_provider is not None and interpretation is not None:
        raise ValueError("Choose either a governed role run or a supplied replay interpretation, not both.")
    if role_provider is not None and role_output_dir is None:
        raise ValueError("role_output_dir is required when role_provider is supplied.")

    env = PerceptionRunEnvelope()
    env.doctrine_authoritative = is_authoritative()
    unresolved = unresolved_contested_decisions()
    env.contested_decisions_unresolved = [decision.id for decision in unresolved]

    runtime_case = copy.deepcopy(dict(case))
    runtime_case.setdefault("decision_time", decision_time)
    runtime_case.setdefault("candidate_objects", {})

    if timeframe_dfs:
        configs = dict(atlas_configs or {})
        if atlas_config is not None:
            configs.setdefault(atlas_config.timeframe, atlas_config)
        atlas_results = atlas_mod.build_multi_timeframe(
            timeframe_dfs,
            decision_time=_timestamp(decision_time),
            configs=configs,
        )
        candidate_objects = runtime_case.get("candidate_objects")
        if not isinstance(candidate_objects, Mapping):
            raise ValueError("case.candidate_objects must be a mapping")
        merged = copy.deepcopy(dict(candidate_objects))
        for timeframe, result in atlas_results.items():
            buckets = merged.get(timeframe)
            if not isinstance(buckets, Mapping):
                buckets = {}
            buckets = copy.deepcopy(dict(buckets))
            buckets["atlas_candidates"] = [candidate.to_dict() for candidate in result.candidates]
            merged[timeframe] = buckets
        runtime_case["candidate_objects"] = merged
        env.atlas_built = True
        env.atlas_candidate_counts = {tf: len(result.candidates) for tf, result in atlas_results.items()}
        env.atlas_sha256 = object_sha256({tf: result.atlas_sha256 for tf, result in atlas_results.items()})
    elif candidate_pool is not None:
        env.atlas_sha256 = object_sha256(
            [dict(candidate) for candidate in candidate_pool if isinstance(candidate, Mapping)]
        )

    context = build_candidate_payload(runtime_case, design="anchor", anchor_fill_budget=fill_budget)
    env.context_sha256 = str(context["stats"].get("context_sha256") or "")

    resolved_interpretation: Mapping[str, Any]
    abstention_requested = False
    if role_provider is not None:
        output_root = Path(role_output_dir).expanduser().resolve()
        manifest = run_structure_lab(
            case=runtime_case,
            provider=role_provider,
            output_dir=output_root,
            annotation_renderer=annotation_renderer,
            candidate_payload_design="anchor",
        )
        outputs_path = output_root / "ai_structure_lab_outputs.json"
        outputs = json.loads(outputs_path.read_text(encoding="utf-8"))
        resolved_interpretation = _interpretation_from_role_outputs(outputs, manifest)
        env.role_run_executed = True
        env.role_run_status = str(manifest.get("final_status") or "UNKNOWN")
        env.role_run_manifest_sha256 = file_sha256(output_root / "ai_structure_lab_manifest.json")
        env.interpretation_source = "GOVERNED_SIX_ROLE_AI_PANEL"
        env.annotation_render_status = str((manifest.get("annotation_render") or {}).get("status") or "NOT_RENDERED")
        abstention_requested = env.role_run_status != "AI_PANEL_COMPLETE"
    elif interpretation is not None:
        resolved_interpretation = dict(interpretation)
        env.interpretation_source = "SUPPLIED_REPLAY_FIXTURE"
    else:
        resolved_interpretation = {}
        env.interpretation_source = "NONE"
        abstention_requested = True

    certification = certify_interpretation(
        resolved_interpretation,
        runtime_case,
        decision_time=decision_time,
        per_timeframe_cutoff=per_timeframe_cutoff,
        abstention_requested=abstention_requested,
        candidate_overrides=candidate_overrides,
    )

    if not env.doctrine_authoritative:
        certification = dict(certification)
        certification["certified"] = False
        certification["abstained"] = True
        certification["abstention_reason"] = (
            "Market Structure Constitution V1 is PROPOSED and is not authority; "
            f"{len(unresolved)} contested decisions remain unresolved."
        )
    elif env.interpretation_source == "NONE":
        certification = dict(certification)
        certification["certified"] = False
        certification["abstained"] = True
        certification["abstention_reason"] = "No governed AI role output or replay interpretation was supplied."

    env.certification = certification
    env.abstention_reason = str(certification.get("abstention_reason") or "")
    return env


def _interpretation_from_role_outputs(
    outputs: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate governed role outputs into the validator's canonical claim."""
    causal = outputs.get("causal_episode_constructor") or {}
    critic = outputs.get("adversarial_structure_critic") or {}
    reconciler = outputs.get("deterministic_candidate_reconciler") or {}
    annotation = outputs.get("annotation_planner") or {}
    evidence_ids = _ordered_unique(
        list(causal.get("active_leg_evidence_ids") or [])
        + list(causal.get("protected_point_evidence_ids") or [])
        + list(causal.get("event_sequence_evidence_ids") or [])
        + list(causal.get("liquidity_evidence_ids") or [])
        + ([causal.get("selected_poi_evidence_id")] if causal.get("selected_poi_evidence_id") else [])
        + list(reconciler.get("accepted_evidence_ids") or [])
        + [
            selection.get("semantic_object_id")
            for selection in annotation.get("selections") or []
            if isinstance(selection, Mapping) and selection.get("semantic_object_id")
        ]
    )
    timeframe = causal.get("controlling_timeframe")
    interpretation: dict[str, Any] = {
        "schema": "certified_structure_interpretation_v1",
        "structure_claims": [{
            "claim_id": "governed_causal_episode",
            "claim_type": str(causal.get("classification") or "UNCLEAR").lower(),
            "timeframe": timeframe,
            "direction": causal.get("parent_external_state") or "unclear",
            "evidence_ids": evidence_ids,
        }],
        "evidence_ids": evidence_ids,
        "causal_story": str(causal.get("causal_story") or ""),
        "role_run_sha256": manifest.get("run_sha256"),
    }
    protected = list(causal.get("protected_point_evidence_ids") or [])
    if protected:
        interpretation["protected_point"] = {
            "object_id": protected[0],
            "evidence_ids": protected,
        }
    if critic.get("verdict") != "PASS" or manifest.get("final_status") != "AI_PANEL_COMPLETE":
        interpretation["abstention_reason"] = (
            f"AI panel not clear: critic={critic.get('verdict')}, "
            f"run={manifest.get('final_status')}."
        )
    return interpretation


def _ordered_unique(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if isinstance(value, str) and value))


def _timestamp(value: str):
    import pandas as pd

    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


__all__ = ["PerceptionRunEnvelope", "run_perception_programme"]
