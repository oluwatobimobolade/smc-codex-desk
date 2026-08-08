"""Hash-sealed authority bundle for the external AI reasoning seat."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
import pandas as pd

from smc_desk.evaluation.perception_gauntlet import gauntlet_protocol_manifest
from smc_desk.evaluation.semantic_metamorphic import vertical_mirror


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AI_SEAT_PROFILE_PATH = REPOSITORY_ROOT / "docs" / "AI_SEAT_MASTER_INSTRUCTIONS.md"
CONSTITUTION_PATH = REPOSITORY_ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V2.yaml"
CONSTITUTION_SEAL_PATH = REPOSITORY_ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V2.sha256"

PROFILE_PACKET_NAME = "00_AI_SEAT_PROFILE.md"
CONSTITUTION_PACKET_NAME = "00_MARKET_STRUCTURE_CONSTITUTION_V2.yaml"
GAUNTLET_PACKET_NAME = "00_PERCEPTION_GAUNTLET_PROTOCOL.json"
AUTHORITY_MANIFEST_PACKET_NAME = "00_authority_manifest.json"
METAMORPHIC_PACKET_NAME = "00_SEMANTIC_METAMORPHIC_EVIDENCE.json"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_profile_metadata(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        raise ValueError("AI seat profile must start with YAML front matter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("AI seat profile YAML front matter is incomplete")
    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("AI seat profile metadata must be a mapping")
    metadata = dict(metadata)
    if metadata.get("schema") != "ai_seat_profile_v1":
        raise ValueError("AI seat profile schema must be ai_seat_profile_v1")
    if metadata.get("status") != "PROPOSED_AI_SEAT_PROFILE_OBSERVE_ONLY":
        raise ValueError("AI seat profile must remain proposed and observe-only")
    authority = metadata.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("AI seat profile authority contract is missing")
    forbidden_true = (
        "signal_allowed",
        "paper_execution_allowed",
        "live_execution_allowed",
        "self_certification_allowed",
    )
    if any(authority.get(key) is not False for key in forbidden_true):
        raise ValueError("AI seat profile attempted to grant forbidden authority")
    if authority.get("independent_validation_required") is not True:
        raise ValueError("AI seat profile must require independent validation")
    return metadata


def load_ai_seat_profile() -> tuple[str, dict[str, Any]]:
    text = AI_SEAT_PROFILE_PATH.read_text(encoding="utf-8")
    return text, parse_profile_metadata(text)


def load_constitution_document() -> dict[str, Any]:
    payload = yaml.safe_load(CONSTITUTION_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("Market Structure Constitution V2 must be a mapping")
    return dict(payload)


def build_metamorphic_evidence(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    windows = evidence_pack.get("ohlcv_windows") or {}
    if isinstance(windows, Mapping):
        for timeframe in ("1d", "4h", "1h", "15m", "5m"):
            rows = windows.get(timeframe)
            if not isinstance(rows, list) or len(rows) < 2:
                continue
            frame = pd.DataFrame(rows)
            required = {"timestamp", "open", "high", "low", "close"}
            if not required.issubset(frame.columns):
                continue
            try:
                transformed, contract = vertical_mirror(frame)
            except (TypeError, ValueError, KeyError):
                continue
            contract_id = f"metamorphic:vertical_mirror:{timeframe}:{contract['source_sha256'][:16]}"
            variants[timeframe] = {
                "evidence_contract_id": contract_id,
                "contract": contract,
                "transformed_ohlcv": json.loads(
                    transformed.to_json(orient="records", date_format="iso", date_unit="ms")
                ),
            }
    payload = {
        "schema": "ai_seat_semantic_metamorphic_evidence_v1",
        "transformation": "vertical_mirror",
        "status": "AVAILABLE" if variants else "NOT_AVAILABLE_NO_VALID_OHLCV_WINDOW",
        "timeframes": variants,
        "authority_contract": {
            "mechanical_artifact_only": True,
            "semantic_symmetry_self_certified": False,
            "independent_comparison_required": True,
            "signal_allowed": False,
        },
    }
    payload["payload_sha256"] = sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    )
    return payload


def build_authority_bundle(evidence_pack: Mapping[str, Any]) -> dict[str, Any]:
    profile_text, profile_metadata = load_ai_seat_profile()
    constitution_bytes = CONSTITUTION_PATH.read_bytes()
    constitution = load_constitution_document()
    constitution_hash = sha256_bytes(constitution_bytes)
    recorded_hash = CONSTITUTION_SEAL_PATH.read_text(encoding="utf-8").strip().split()[0]
    violations: list[str] = []
    if constitution_hash != recorded_hash:
        violations.append("constitution_seal_mismatch")
    if constitution.get("status") != "PROPOSED_RESEARCH_DOCTRINE_NO_EXECUTION_AUTHORITY":
        violations.append("unexpected_constitution_authority_status")
    authority = constitution.get("authority_contract") or {}
    for key in ("signal_allowed", "paper_execution_allowed", "live_execution_allowed"):
        if authority.get(key) is not False:
            violations.append(f"constitution_forbidden_authority:{key}")

    contested = constitution.get("contested_decisions") or []
    pending = [
        str(item.get("id"))
        for item in contested
        if isinstance(item, Mapping) and item.get("status") == "PENDING_HUMAN_ADJUDICATION"
    ]
    gauntlet = gauntlet_protocol_manifest()
    metamorphic = build_metamorphic_evidence(evidence_pack)
    metamorphic_bytes = json.dumps(metamorphic, indent=2, sort_keys=True, default=str).encode("utf-8")
    episode_graph = evidence_pack.get("formal_causal_episode_graph") or {}
    graph_invariants = episode_graph.get("invariants") if isinstance(episode_graph, Mapping) else {}
    manifest = {
        "schema": "ai_smc_authority_manifest_v1",
        "status": "PASS" if not violations else "FATAL_AUTHORITY_VIOLATION",
        "violations": violations,
        "ai_seat_profile": {
            "schema": profile_metadata["schema"],
            "version": profile_metadata.get("version"),
            "status": profile_metadata["status"],
            "source_path": str(AI_SEAT_PROFILE_PATH),
            "packet_path": PROFILE_PACKET_NAME,
            "sha256": sha256_bytes(profile_text.encode("utf-8")),
            "authority": dict(profile_metadata["authority"]),
        },
        "constitution": {
            "schema": constitution.get("schema"),
            "version": constitution.get("version"),
            "status": constitution.get("status"),
            "source_path": str(CONSTITUTION_PATH),
            "packet_path": CONSTITUTION_PACKET_NAME,
            "sha256": constitution_hash,
            "recorded_sha256": recorded_hash,
            "seal_matches": constitution_hash == recorded_hash,
            "pending_human_adjudication": pending,
            "pending_count": len(pending),
            "authority_contract": dict(authority),
        },
        "gauntlet": {
            "schema": gauntlet["schema"],
            "version": gauntlet["version"],
            "protocol_sha256": gauntlet["protocol_sha256"],
            "packet_path": GAUNTLET_PACKET_NAME,
            "self_scoring_allowed": False,
            "score_meaning": "protocol_conformance_not_perception_accuracy",
        },
        "metamorphic_evidence": {
            "schema": metamorphic["schema"],
            "status": metamorphic["status"],
            "packet_path": METAMORPHIC_PACKET_NAME,
            "sha256": sha256_bytes(metamorphic_bytes),
            "payload_sha256": metamorphic["payload_sha256"],
            "available_timeframes": sorted(metamorphic["timeframes"]),
            "evidence_contract_ids": [
                item["evidence_contract_id"] for item in metamorphic["timeframes"].values()
            ],
            "required_for_station": "S08_MECHANICAL_MIRROR",
        },
        "graph_authority": {
            "formal_structure_graph_present": isinstance(evidence_pack.get("formal_structure_graph"), Mapping),
            "formal_causal_episode_graph_present": isinstance(episode_graph, Mapping) and bool(episode_graph),
            "formal_causal_episode_graph_schema": episode_graph.get("schema") if isinstance(episode_graph, Mapping) else None,
            "formal_causal_episode_graph_invariant_status": graph_invariants.get("status") if isinstance(graph_invariants, Mapping) else None,
            "causal_graph_can_only_downgrade": True,
            "ai_can_promote_around_graph": False,
        },
        "typed_authority": {
            "market_truth": "closed_ohlcv_timestamps_source_provenance",
            "semantic_truth": "versioned_constitution_with_pending_decisions_preserved",
            "operational_interpretation": "deterministic_candidates_and_graphs_under_named_versions",
            "ai_role": "relevance_story_dissent_annotation_selection_only",
            "validation_role": "independent_downgrade_or_refusal_only",
            "empirical_truth": "independent_adjudication_and_outcomes_not_self_score",
        },
        "authority_contract": {
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
            "self_certification_allowed": False,
            "independent_validation_required": True,
        },
    }
    return {
        "profile_text": profile_text,
        "constitution_bytes": constitution_bytes,
        "constitution_document": constitution,
        "gauntlet_protocol": gauntlet,
        "metamorphic_evidence": metamorphic,
        "authority_manifest": manifest,
    }


def verify_bundled_authority(packet_dir: Path) -> list[str]:
    root = Path(packet_dir)
    manifest_path = root / AUTHORITY_MANIFEST_PACKET_NAME
    if not manifest_path.exists():
        return ["missing_authority_manifest"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ["invalid_authority_manifest"]
    issues: list[str] = []
    if manifest.get("status") != "PASS":
        issues.append("authority_manifest_not_pass")
    bindings = (
        ("ai_seat_profile", "sha256"),
        ("constitution", "sha256"),
    )
    for section, hash_key in bindings:
        record = manifest.get(section) or {}
        path = root / str(record.get("packet_path") or "")
        if not path.is_file():
            issues.append(f"missing_bundled_authority:{section}")
        elif sha256_file(path) != record.get(hash_key):
            issues.append(f"bundled_authority_hash_mismatch:{section}")
    gauntlet_record = manifest.get("gauntlet") or {}
    gauntlet_path = root / str(gauntlet_record.get("packet_path") or "")
    if not gauntlet_path.is_file():
        issues.append("missing_bundled_authority:gauntlet")
    else:
        try:
            protocol = json.loads(gauntlet_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            protocol = {}
        if protocol.get("protocol_sha256") != gauntlet_record.get("protocol_sha256"):
            issues.append("bundled_authority_hash_mismatch:gauntlet_protocol")
    metamorphic_record = manifest.get("metamorphic_evidence") or {}
    metamorphic_path = root / str(metamorphic_record.get("packet_path") or "")
    if not metamorphic_path.is_file():
        issues.append("missing_bundled_authority:metamorphic_evidence")
    elif sha256_file(metamorphic_path) != metamorphic_record.get("sha256"):
        issues.append("bundled_authority_hash_mismatch:metamorphic_evidence")
    return issues


__all__ = [
    "AI_SEAT_PROFILE_PATH",
    "AUTHORITY_MANIFEST_PACKET_NAME",
    "CONSTITUTION_PACKET_NAME",
    "GAUNTLET_PACKET_NAME",
    "METAMORPHIC_PACKET_NAME",
    "PROFILE_PACKET_NAME",
    "build_authority_bundle",
    "build_metamorphic_evidence",
    "load_ai_seat_profile",
    "load_constitution_document",
    "parse_profile_metadata",
    "sha256_file",
    "verify_bundled_authority",
]
