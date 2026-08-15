"""Autonomous, human-independent definition-conformance contracts.

This module never promotes a market mechanism, forecast, strategy, or trade.
It answers a narrower question: did two independent implementations emit the
same normalized claims for the same closed data and frozen house definition?
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from smc_desk.data.hashing import file_sha256, object_sha256


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONSTITUTION_PATH = ROOT / "specs" / "AUTONOMOUS_TRUTH_CONSTITUTION_V1.yaml"
DEFAULT_SEAL_PATH = ROOT / "specs" / "AUTONOMOUS_TRUTH_CONSTITUTION_V1.sha256"
EXPECTED_SCHEMA = "smc_codex_autonomous_truth_constitution_v1"
EXPECTED_VERSION = "1.0.0"
ACTIVE_STATUS = "ACTIVE_RESEARCH_CERTIFICATION_CONTRACT"

CERTIFICATE_STATUSES = {
    "DEFINITION_CONFORMANT",
    "IMPLEMENTATION_CONFLICT",
    "BOUNDARY_SENSITIVE",
    "DOCTRINE_UNDEFINED",
    "DATA_FAILED",
    "NOT_EVALUATED",
}


@dataclass(frozen=True)
class AutonomousTruthConstitution:
    document: Mapping[str, Any]
    sha256: str
    path: Path

    @property
    def label_contracts(self) -> Mapping[str, Any]:
        return self.document["executable_label_contracts"]

    @property
    def profiles(self) -> Mapping[str, Any]:
        return self.document["robustness_envelopes"]["profiles"]


def load_autonomous_truth_constitution(
    path: str | Path = DEFAULT_CONSTITUTION_PATH,
    seal_path: str | Path = DEFAULT_SEAL_PATH,
) -> AutonomousTruthConstitution:
    source = Path(path)
    seal = Path(seal_path)
    if not source.is_file():
        raise FileNotFoundError(f"Autonomous truth constitution is missing: {source}")
    if not seal.is_file():
        raise FileNotFoundError(f"Autonomous truth constitution seal is missing: {seal}")
    digest = file_sha256(source)
    if seal.read_text(encoding="utf-8").strip() != digest:
        raise ValueError("Autonomous truth constitution hash mismatch.")
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("Autonomous truth constitution must be a YAML mapping.")
    if document.get("schema") != EXPECTED_SCHEMA or document.get("version") != EXPECTED_VERSION:
        raise ValueError("Unexpected autonomous truth constitution schema or version.")
    if document.get("status") != ACTIVE_STATUS:
        raise ValueError("Autonomous truth constitution is not the active research contract.")
    authority = document.get("authority_contract") or {}
    prohibited = (
        "signal_allowed",
        "paper_execution_allowed",
        "live_execution_allowed",
        "predictive_edge_claim_allowed",
    )
    if any(bool(authority.get(key)) for key in prohibited):
        raise ValueError("Autonomous definition conformance cannot grant prediction or execution authority.")
    if authority.get("human_adjudication_required_for_definition_conformance") is not False:
        raise ValueError("Definition conformance must be explicitly independent of human adjudication.")
    return AutonomousTruthConstitution(document=document, sha256=digest, path=source)


def normalized_claim_signature(claim: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the exact semantic/geometry identity used by both oracles.

    Narrative text, confidence, detector ids, and incidental metadata are
    excluded. Prices are emitted by the oracles as canonical decimal strings.
    """
    return (
        str(claim.get("label_family") or ""),
        str(claim.get("timeframe") or ""),
        str(claim.get("scope") or ""),
        str(claim.get("direction") or ""),
        str(claim.get("pivot_time") or ""),
        str(claim.get("candidate_at") or ""),
        str(claim.get("confirmed_at") or ""),
        str(claim.get("price_low") or ""),
        str(claim.get("price_high") or ""),
        str(claim.get("reference_time") or ""),
        str(claim.get("reference_price") or ""),
        str(claim.get("state") or ""),
    )


def compare_claim_sets(
    *,
    label_family: str,
    reference_claims: Iterable[Mapping[str, Any]],
    production_claims: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    reference = {normalized_claim_signature(item) for item in reference_claims}
    production = {normalized_claim_signature(item) for item in production_claims}
    missing = sorted(reference - production)
    unexpected = sorted(production - reference)
    status = "DEFINITION_CONFORMANT" if not missing and not unexpected else "IMPLEMENTATION_CONFLICT"
    return {
        "schema": "autonomous_claim_set_comparison_v1",
        "label_family": label_family,
        "status": status,
        "reference_count": len(reference),
        "production_count": len(production),
        "matched_count": len(reference & production),
        "missing_from_production": [list(item) for item in missing],
        "unexpected_from_production": [list(item) for item in unexpected],
        "reference_claim_set_sha256": object_sha256(sorted(reference)),
        "production_claim_set_sha256": object_sha256(sorted(production)),
    }


def evaluate_robustness_envelope(
    claims_by_profile: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Separate profile-invariant claims from threshold-sensitive claims.

    Certificates carry exact hashes/counts plus bounded audit examples.  The
    full per-profile claims remain in the run artifact, avoiding multi-megabyte
    certificate duplication inside every downstream evidence pack.
    """
    example_limit = 20
    if not claims_by_profile:
        return {
            "schema": "autonomous_robustness_envelope_v2",
            "status": "DOCTRINE_UNDEFINED",
            "profiles": [],
            "robust_claims_sample": [],
            "boundary_sensitive_claims_sample": [],
            "robust_claim_set_sha256": object_sha256([]),
            "boundary_sensitive_claim_set_sha256": object_sha256([]),
            "sample_limit": example_limit,
        }
    profile_sets = {
        name: {normalized_claim_signature(item) for item in claims}
        for name, claims in claims_by_profile.items()
    }
    values = list(profile_sets.values())
    intersection = set.intersection(*values) if values else set()
    union = set.union(*values) if values else set()
    sensitive = union - intersection
    robust_sorted = sorted(intersection)
    sensitive_sorted = sorted(sensitive)
    return {
        "schema": "autonomous_robustness_envelope_v2",
        "status": "ROBUST" if not sensitive else "BOUNDARY_SENSITIVE",
        "profiles": sorted(profile_sets),
        "profile_counts": {name: len(items) for name, items in sorted(profile_sets.items())},
        "profile_claim_set_sha256": {
            name: object_sha256(sorted(items)) for name, items in sorted(profile_sets.items())
        },
        "robust_claims_sample": [list(item) for item in robust_sorted[:example_limit]],
        "boundary_sensitive_claims_sample": [
            list(item) for item in sensitive_sorted[:example_limit]
        ],
        "robust_claim_set_sha256": object_sha256(robust_sorted),
        "boundary_sensitive_claim_set_sha256": object_sha256(sensitive_sorted),
        "sample_limit": example_limit,
        "robust_count": len(intersection),
        "boundary_sensitive_count": len(sensitive),
    }


def issue_definition_conformance_certificate(
    *,
    market: str,
    timeframe: str,
    decision_time: str,
    data_sha256: str,
    reference_oracle: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
    robustness: Mapping[str, Any],
    evaluated_label_families: Sequence[str],
    unevaluated_label_families: Sequence[str],
    metamorphic_results: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    constitution = load_autonomous_truth_constitution()
    failures = [
        str(item.get("label_family") or "unknown")
        for item in comparisons
        if item.get("status") != "DEFINITION_CONFORMANT"
    ]
    metamorphic_failures = [
        str(item.get("relation") or "unknown")
        for item in metamorphic_results
        if item.get("passed") is not True
    ]
    if failures or metamorphic_failures:
        status = "IMPLEMENTATION_CONFLICT"
    elif robustness.get("status") == "BOUNDARY_SENSITIVE":
        status = "BOUNDARY_SENSITIVE"
    elif robustness.get("status") == "DOCTRINE_UNDEFINED":
        status = "DOCTRINE_UNDEFINED"
    elif not evaluated_label_families:
        status = "NOT_EVALUATED"
    else:
        status = "DEFINITION_CONFORMANT"
    if status not in CERTIFICATE_STATUSES:
        raise ValueError(f"Unsupported autonomous certificate status: {status}")
    payload = {
        "schema": "autonomous_definition_conformance_certificate_v1",
        "status": status,
        "scope": {
            "market": market,
            "timeframe": timeframe,
            "decision_time": decision_time,
            "definition_version": constitution.document["version"],
            "evidence_layer": "definition_conformance",
        },
        "source": {
            "data_sha256": data_sha256,
            "constitution_sha256": constitution.sha256,
            "reference_oracle": dict(reference_oracle),
        },
        "evaluated_label_families": sorted(set(evaluated_label_families)),
        "unevaluated_label_families": sorted(set(unevaluated_label_families)),
        "comparisons": list(comparisons),
        "robustness": dict(robustness),
        "metamorphic_results": list(metamorphic_results),
        "failures": failures,
        "metamorphic_failures": metamorphic_failures,
        "authority_contract": {
            "human_adjudication_used": False,
            "ai_vote_used": False,
            "universal_smc_truth_claimed": False,
            "mechanism_authority": False,
            "forecast_authority": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }
    payload["certificate_sha256"] = object_sha256(payload)
    return payload


__all__ = [
    "AutonomousTruthConstitution",
    "CERTIFICATE_STATUSES",
    "compare_claim_sets",
    "evaluate_robustness_envelope",
    "issue_definition_conformance_certificate",
    "load_autonomous_truth_constitution",
    "normalized_claim_signature",
]
