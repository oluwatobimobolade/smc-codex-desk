"""Governed sequential runtime for the six AI structure reasoning roles."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from pydantic import ValidationError

from smc_desk.brain.structure_lab.prompts import build_role_prompt
from smc_desk.brain.structure_lab.schemas import ROLE_SCHEMAS
from smc_desk.brain.structure_reasoning_roles import REQUIRED_ROLES
from smc_desk.data.hashing import file_sha256, object_sha256, sha256_text


@dataclass(frozen=True)
class RoleCompletion:
    raw: str | Mapping[str, Any]
    provider_name: str
    model_name: str
    provider_mode: str
    metadata: dict[str, Any]


class StructureRoleProvider(Protocol):
    provider_name: str
    model_name: str
    provider_mode: str

    def complete(self, role: str, prompt: str, payload: Mapping[str, Any], attempt: int) -> RoleCompletion:
        ...


class ReplayRoleProvider:
    """Offline deterministic provider for tests and replay, never real reasoning."""

    provider_name = "offline_structure_role_replay"
    model_name = "recorded-role-json"
    provider_mode = "OFFLINE_REPLAY_PROVIDER"

    def __init__(self, responses: Mapping[str, Any]):
        self.responses = dict(responses)

    def complete(self, role: str, prompt: str, payload: Mapping[str, Any], attempt: int) -> RoleCompletion:
        if role not in self.responses:
            raise KeyError(f"No replay response registered for role: {role}")
        value = self.responses[role]
        if isinstance(value, list):
            index = min(attempt, len(value) - 1)
            value = value[index]
        return RoleCompletion(
            raw=value,
            provider_name=self.provider_name,
            model_name=self.model_name,
            provider_mode=self.provider_mode,
            metadata={"replay": True, "attempt": attempt, "real_ai_reasoning": False},
        )


class CallableRoleProvider:
    """Adapter for real vision AI, external agents, or manual AI JSON.

    Provider mode is explicit so a local deterministic function cannot be
    mislabeled as genuine chart reasoning.
    """

    VALID_MODES = {
        "REAL_VISION_LLM_PROVIDER",
        "EXTERNAL_AI_AGENT",
        "MANUAL_AI_ASSISTED_JSON",
        "LOCAL_DETERMINISTIC_PROVIDER",
    }

    def __init__(
        self,
        completion_fn,
        *,
        provider_name: str,
        model_name: str,
        provider_mode: str,
    ):
        if provider_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported role provider mode: {provider_mode}")
        self.completion_fn = completion_fn
        self.provider_name = provider_name
        self.model_name = model_name
        self.provider_mode = provider_mode

    def complete(self, role: str, prompt: str, payload: Mapping[str, Any], attempt: int) -> RoleCompletion:
        raw = self.completion_fn(role, prompt, payload, attempt)
        return RoleCompletion(
            raw=raw,
            provider_name=self.provider_name,
            model_name=self.model_name,
            provider_mode=self.provider_mode,
            metadata={
                "adapter": "callable_role_provider",
                "attempt": attempt,
                "real_ai_reasoning": self.provider_mode in {
                    "REAL_VISION_LLM_PROVIDER",
                    "EXTERNAL_AI_AGENT",
                    "MANUAL_AI_ASSISTED_JSON",
                },
                "real_api_call": self.provider_mode == "REAL_VISION_LLM_PROVIDER",
            },
        )


def run_structure_lab(
    *,
    case: Mapping[str, Any],
    provider: StructureRoleProvider,
    output_dir: str | Path,
    max_repair_attempts: int = 1,
    annotation_renderer: Callable[[Mapping[str, Any], Mapping[str, Any], Path], Mapping[str, Any]] | None = None,
    candidate_payload_design: str | None = None,
) -> dict[str, Any]:
    if max_repair_attempts not in {0, 1}:
        raise ValueError("Structure lab permits at most one bounded repair attempt.")
    if candidate_payload_design not in {None, "full", "flat", "anchor"}:
        raise ValueError(
            "Runtime supports full, flat, or anchor payloads. anchor_tools is an A/B prompt "
            "surface only until a bounded tool-call execution loop exists."
        )
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _validate_case_contract(case)
    runtime_case = dict(case)
    allowed_evidence_ids = _collect_evidence_ids(
        {"candidates": case["candidate_objects"], "graph": case["formal_structure_graph"]}
    )
    outputs: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []

    for order, role in enumerate(REQUIRED_ROLES, start=1):
        role_payload = _role_input(role, runtime_case, outputs)
        prompt_packet = build_role_prompt(
            role,
            role_payload,
            candidate_payload_design=candidate_payload_design,
        )
        parsed, audit, raw_text = _complete_validated_role(
            role=role,
            prompt_packet=prompt_packet,
            payload=role_payload,
            provider=provider,
            max_repair_attempts=max_repair_attempts,
            allowed_evidence_ids=allowed_evidence_ids,
        )
        stage_order = order + 1 if annotation_renderer is not None and role == "visual_annotation_critic" else order
        role_dir = root / f"{stage_order:02d}_{role}"
        role_dir.mkdir(parents=True, exist_ok=True)
        (role_dir / "prompt.txt").write_text(prompt_packet["prompt"] + "\n", encoding="utf-8")
        (role_dir / "raw_response.json").write_text(raw_text + "\n", encoding="utf-8")
        _write_json(role_dir / "parsed_response.json", parsed)
        _write_json(role_dir / "role_audit.json", audit)
        outputs[role] = parsed
        audits.append(audit)
        if role == "annotation_planner" and annotation_renderer is not None:
            render_dir = root / "06_professional_annotation_render"
            render_manifest = dict(annotation_renderer(parsed, outputs, render_dir))
            runtime_case["render_manifest"] = render_manifest
            _write_json(render_dir / "render_manifest.json", render_manifest)

    critic = outputs["adversarial_structure_critic"]
    visual_critic = outputs["visual_annotation_critic"]
    render_manifest = runtime_case.get("render_manifest") or {"status": "NOT_RENDERED"}
    if (
        critic["verdict"] == "DOWNGRADE"
        or visual_critic["verdict"] == "DOWNGRADE"
        or render_manifest.get("status") == "REVIEW_REQUIRED"
    ):
        final_status = "REVIEW_REQUIRED"
    elif critic["verdict"] == "REVISE" or visual_critic["verdict"] == "CLEANUP":
        final_status = "REVISION_REQUIRED"
    else:
        final_status = "AI_PANEL_COMPLETE"

    manifest = {
        "schema": "ai_structure_lab_run_v1",
        "case_id": case["case_id"],
        "symbol": case["symbol"],
        "decision_time": case["decision_time"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider_name": provider.provider_name,
        "model_name": provider.model_name,
        "provider_mode": provider.provider_mode,
        "candidate_payload_design": candidate_payload_design or "flat",
        "retrieval_tools_advertised": False,
        "retrieval_tools_executed": False,
        "role_order": list(REQUIRED_ROLES),
        "role_audits": audits,
        "annotation_render": {
            "status": render_manifest.get("status"),
            "render_manifest_sha256": render_manifest.get("render_manifest_sha256"),
            "rendered_image_count": render_manifest.get("rendered_image_count", 0),
            "timeframes": render_manifest.get("timeframes", []),
            "all_planned_objects_rendered": render_manifest.get("all_planned_objects_rendered", False),
            "pixel_review_status": render_manifest.get("pixel_review_status"),
        },
        "final_status": final_status,
        "truth_class": "AI_WEAK_CONSENSUS_ONLY",
        "human_gold_created": False,
        "signal_allowed": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
    }
    manifest["run_sha256"] = object_sha256(
        {
            "case": dict(case),
            "outputs": outputs,
            "audits": audits,
            "render_manifest": render_manifest,
            "candidate_payload_design": candidate_payload_design or "flat",
            "final_status": final_status,
        }
    )
    _write_json(root / "ai_structure_lab_manifest.json", manifest)
    _write_json(root / "ai_structure_lab_outputs.json", outputs)
    return manifest


def _complete_validated_role(
    *,
    role: str,
    prompt_packet: dict[str, Any],
    payload: dict[str, Any],
    provider: StructureRoleProvider,
    max_repair_attempts: int,
    allowed_evidence_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    errors: list[str] = []
    for attempt in range(max_repair_attempts + 1):
        repair_payload = payload if not errors else {**payload, "repair_errors": list(errors)}
        completion = provider.complete(role, prompt_packet["prompt"], repair_payload, attempt)
        raw_text = completion.raw if isinstance(completion.raw, str) else json.dumps(completion.raw, sort_keys=True, default=str)
        try:
            raw_object = json.loads(raw_text)
            model = ROLE_SCHEMAS[role].model_validate(raw_object)
            parsed = model.model_dump(mode="json", by_alias=True)
            _validate_evidence_grounding(role, parsed, allowed_evidence_ids)
            _validate_role_output_against_input(role, parsed, repair_payload)
            audit = {
                "schema": "structure_role_audit_v1",
                "role": role,
                "provider_name": completion.provider_name,
                "model_name": completion.model_name,
                "provider_mode": completion.provider_mode,
                "attempts_used": attempt + 1,
                "repair_used": attempt > 0,
                "prompt_sha256": prompt_packet["prompt_sha256"],
                "input_sha256": object_sha256(repair_payload),
                "raw_response_sha256": sha256_text(raw_text),
                "parsed_response_sha256": object_sha256(parsed),
                "metadata": completion.metadata,
            }
            return parsed, audit, raw_text
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            errors.append(str(exc))
    raise ValueError(f"Role {role} failed after bounded repair: {errors}")


def _role_input(role: str, case: Mapping[str, Any], outputs: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {"case_id": case["case_id"], "symbol": case["symbol"], "decision_time": case["decision_time"]}
    if role == "blind_visual_structure_reader":
        return {**metadata, "chart_manifest": case["chart_manifest"]}
    if role == "deterministic_candidate_reconciler":
        return {
            **metadata,
            "blind_visual_read": outputs["blind_visual_structure_reader"],
            "candidate_objects": case["candidate_objects"],
            "formal_structure_graph": case["formal_structure_graph"],
        }
    if role == "causal_episode_constructor":
        return {
            **metadata,
            "reconciliation": outputs["deterministic_candidate_reconciler"],
            "formal_structure_graph": case["formal_structure_graph"],
        }
    if role == "adversarial_structure_critic":
        return {
            **metadata,
            "causal_episode": outputs["causal_episode_constructor"],
            "formal_structure_graph": case["formal_structure_graph"],
            "invariants": case["formal_structure_graph"].get("invariants", {}),
        }
    if role == "annotation_planner":
        return {
            **metadata,
            "causal_episode": outputs["causal_episode_constructor"],
            "critic_review": outputs["adversarial_structure_critic"],
            "candidate_objects": case["candidate_objects"],
        }
    return {
        **metadata,
        "annotation_plan": outputs["annotation_planner"],
        "render_manifest": case.get("render_manifest", {"status": "NOT_RENDERED"}),
        "formal_structure_graph": case["formal_structure_graph"],
    }


def _validate_case_contract(case: Mapping[str, Any]) -> None:
    required = {"case_id", "symbol", "decision_time", "chart_manifest", "candidate_objects", "formal_structure_graph"}
    missing = required.difference(case)
    if missing:
        raise ValueError(f"Structure lab case missing fields: {sorted(missing)}")
    if case["formal_structure_graph"].get("authority_contract", {}).get("signal_allowed") is not False:
        raise ValueError("Formal graph must explicitly deny signal authority.")


def _validate_evidence_grounding(role: str, payload: dict[str, Any], allowed: set[str]) -> None:
    if role == "blind_visual_structure_reader":
        return
    referenced = _collect_referenced_evidence_ids(payload)
    invented = sorted(referenced.difference(allowed))
    if invented:
        raise ValueError(f"Invented or unavailable evidence IDs: {invented}")


def _validate_role_output_against_input(
    role: str,
    output: Mapping[str, Any],
    role_input: Mapping[str, Any],
) -> None:
    if role != "visual_annotation_critic":
        return
    render = role_input.get("render_manifest") or {}
    verdict = str(output.get("verdict") or "")
    if verdict != "PASS":
        return
    status = str(render.get("status") or "")
    legacy_rendered = status == "RENDERED" and bool(render.get("image_sha256"))
    certified_rendered = (
        status == "PASS"
        and int(render.get("rendered_image_count") or 0) > 0
        and bool(render.get("all_planned_objects_rendered"))
        and render.get("pixel_review_status") == "PASS"
    )
    if not (legacy_rendered or certified_rendered):
        raise ValueError(
            "Visual critic cannot PASS before a real rendered image, complete object mapping, and pixel review exist."
        )
    if certified_rendered:
        expected_manifest_hash = str(render.get("render_manifest_sha256") or "")
        expected_image_hashes = sorted(
            str(item.get("annotated_sha256"))
            for item in render.get("images") or []
            if isinstance(item, Mapping) and item.get("annotated_sha256")
        )
        if output.get("visual_inspection_basis") != "rendered_images":
            raise ValueError("Visual critic PASS must attest that rendered images were inspected.")
        if output.get("reviewed_render_manifest_sha256") != expected_manifest_hash:
            raise ValueError("Visual critic reviewed_render_manifest_sha256 does not match the rendered chart pack.")
        if sorted(str(value) for value in output.get("reviewed_image_sha256") or []) != expected_image_hashes:
            raise ValueError("Visual critic reviewed_image_sha256 does not match the rendered chart images.")


def _collect_referenced_evidence_ids(value: Any, key: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            if child_key == "semantic_object_id" and isinstance(child, str):
                found.add(child)
            elif child_key.endswith("evidence_id") and isinstance(child, str) and child:
                found.add(child)
            elif child_key.endswith("evidence_ids") and isinstance(child, list):
                found.update(str(item) for item in child if item)
            elif child_key == "visual_to_evidence_map" and isinstance(child, Mapping):
                for mapped in child.values():
                    if isinstance(mapped, list):
                        found.update(str(item) for item in mapped if item)
            else:
                found.update(_collect_referenced_evidence_ids(child, child_key))
    elif isinstance(value, list):
        for child in value:
            found.update(_collect_referenced_evidence_ids(child, key))
    return found


def _collect_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key.endswith("_id") and isinstance(child, str):
                found.add(child)
            elif key.endswith("_ids") and isinstance(child, list):
                found.update(str(item) for item in child if isinstance(item, str))
            found.update(_collect_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_collect_evidence_ids(child))
    return found


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
