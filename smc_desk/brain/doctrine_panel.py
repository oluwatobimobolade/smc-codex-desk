"""AI-first doctrine research packets and weak-consensus synthesis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from smc_desk.data.hashing import file_sha256, object_sha256, sha256_text


DOCTRINE_ROLES = (
    "evidence_researcher",
    "machine_definition_formalizer",
    "counterexample_hunter",
    "doctrine_synthesis_judge",
)


class DoctrineClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    concept: str
    statement: str
    source_ids: list[str]
    status: str
    confidence: float = Field(ge=0, le=1)


class DoctrinePanelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    schema_id: str = Field(alias="schema")
    role: str
    claims: list[DoctrineClaim]
    unresolved_conflicts: list[str]
    recommendations: list[str]


def build_doctrine_source_manifest(paths: list[str | Path]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(paths, start=1):
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        records.append(
            {
                "source_id": f"SRC-{index:03d}",
                "path": str(path),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "text": path.read_text(encoding="utf-8"),
            }
        )
    public_records = [{key: value for key, value in record.items() if key != "text"} for record in records]
    return {
        "schema": "ai_doctrine_source_manifest_v1",
        "sources": records,
        "manifest_sha256": object_sha256(public_records),
    }


def build_doctrine_role_packet(
    role: str,
    *,
    source_manifest: Mapping[str, Any],
    prior_outputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if role not in DOCTRINE_ROLES:
        raise ValueError(f"Unknown doctrine role: {role}")
    sources = list(source_manifest.get("sources") or [])
    instructions = {
        "evidence_researcher": "Extract explicit, repeated, contested, and unsupported SMC claims. Cite source IDs. Do not reconcile conflicts yet.",
        "machine_definition_formalizer": "Translate research claims into testable evidence requirements, prohibited shortcuts, lifecycle, invalidation, and abstention rules.",
        "counterexample_hunter": "Attack every proposed rule with positive, negative, ambiguous, parent-child, wick-only, and insufficient-context counterexamples.",
        "doctrine_synthesis_judge": "Select only defensible pilot doctrine. Preserve contested rules and rejected alternatives. Never modify detector code or claim human consensus.",
    }[role]
    input_payload = {
        "role": role,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "sources": sources if role == "evidence_researcher" else [
            {key: value for key, value in source.items() if key != "text"} for source in sources
        ],
        "prior_outputs": dict(prior_outputs or {}),
    }
    prompt = "\n\n".join(
        [
            "You are one independent role in an AI-first SMC doctrine panel.",
            instructions,
            "All claims require source_ids. Distinguish common doctrine, project policy, contested interpretation, and unproven proposal.",
            "Your output is AI_WEAK_DOCTRINE_RESEARCH, never human gold and never direct runtime authority.",
            "Return strict JSON matching DoctrinePanelOutput.",
            json.dumps(input_payload, sort_keys=True, default=str),
        ]
    )
    return {
        "schema": "ai_doctrine_role_packet_v1",
        "role": role,
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "input_sha256": object_sha256(input_payload),
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "truth_class": "AI_WEAK_DOCTRINE_RESEARCH",
    }


def validate_doctrine_output(
    raw: str | Mapping[str, Any],
    *,
    role: str,
    allowed_source_ids: set[str],
) -> dict[str, Any]:
    payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
    model = DoctrinePanelOutput.model_validate(payload)
    if model.role != role:
        raise ValueError(f"Doctrine output role mismatch: expected {role}, got {model.role}")
    invented = sorted(
        source_id
        for claim in model.claims
        for source_id in claim.source_ids
        if source_id not in allowed_source_ids
    )
    if invented:
        raise ValueError(f"Invented doctrine source IDs: {invented}")
    result = model.model_dump(mode="json", by_alias=True)
    result["truth_class"] = "AI_WEAK_DOCTRINE_RESEARCH"
    result["runtime_authority"] = False
    result["human_gold_created"] = False
    result["output_sha256"] = object_sha256(result)
    return result


def export_doctrine_panel_packets(
    *,
    source_paths: list[str | Path],
    output_dir: str | Path,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_manifest = build_doctrine_source_manifest(source_paths)
    public_manifest = {
        **source_manifest,
        "sources": [
            {key: value for key, value in source.items() if key != "text"}
            for source in source_manifest["sources"]
        ],
    }
    _write_json(root / "source_manifest.json", public_manifest)
    packets: list[dict[str, Any]] = []
    for order, role in enumerate(DOCTRINE_ROLES, start=1):
        packet = build_doctrine_role_packet(role, source_manifest=source_manifest)
        role_dir = root / f"{order:02d}_{role}"
        role_dir.mkdir(parents=True, exist_ok=True)
        (role_dir / "prompt.md").write_text(packet["prompt"] + "\n", encoding="utf-8")
        _write_json(
            role_dir / "response_template.json",
            {
                "schema": f"{role}_output_v1",
                "role": role,
                "claims": [],
                "unresolved_conflicts": [],
                "recommendations": [],
            },
        )
        packets.append({key: value for key, value in packet.items() if key != "prompt"})
    manifest = {
        "schema": "ai_doctrine_panel_export_v1",
        "roles": list(DOCTRINE_ROLES),
        "packets": packets,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "status": "READY_FOR_AI_RESEARCH",
        "truth_class": "AI_WEAK_DOCTRINE_RESEARCH",
        "human_certification_status": "NOT_STARTED",
        "runtime_authority": False,
    }
    manifest["export_sha256"] = object_sha256(manifest)
    _write_json(root / "doctrine_panel_manifest.json", manifest)
    return manifest


def finalize_doctrine_panel(output_dir: str | Path) -> dict[str, Any]:
    """Validate all four AI role outputs and create a non-authoritative synthesis."""
    root = Path(output_dir).expanduser().resolve()
    source_manifest = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    allowed_source_ids = {str(item["source_id"]) for item in source_manifest["sources"]}
    outputs: dict[str, Any] = {}
    for order, role in enumerate(DOCTRINE_ROLES, start=1):
        response_path = root / f"{order:02d}_{role}" / "ai_response.json"
        if not response_path.exists():
            raise FileNotFoundError(f"Missing AI doctrine response: {response_path}")
        outputs[role] = validate_doctrine_output(
            response_path.read_text(encoding="utf-8"),
            role=role,
            allowed_source_ids=allowed_source_ids,
        )
    judge = outputs["doctrine_synthesis_judge"]
    accepted = [claim for claim in judge["claims"] if claim["status"] == "ACCEPT_FOR_PILOT"]
    contested = [claim for claim in judge["claims"] if claim["status"] == "KEEP_CONTESTED"]
    rejected = [claim for claim in judge["claims"] if claim["status"] == "REJECT"]
    result = {
        "schema": "ai_doctrine_panel_result_v1",
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "role_output_hashes": {role: output["output_sha256"] for role, output in outputs.items()},
        "accepted_for_pilot": accepted,
        "contested": contested,
        "rejected": rejected,
        "unresolved_conflicts": judge["unresolved_conflicts"],
        "recommendations": judge["recommendations"],
        "status": "AI_RESEARCH_COMPLETE_AWAITING_CERTIFICATION",
        "truth_class": "AI_WEAK_DOCTRINE_CONSENSUS",
        "runtime_authority": False,
        "detector_modification_allowed": False,
        "human_gold_created": False,
        "human_certification_status": "NOT_STARTED",
    }
    result["result_sha256"] = object_sha256(result)
    _write_json(root / "validated_role_outputs.json", outputs)
    _write_json(root / "ai_doctrine_panel_result.json", result)
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
