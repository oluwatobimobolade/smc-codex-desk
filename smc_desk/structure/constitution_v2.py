"""Integrity-checked loader for the non-authoritative Constitution V2 proposal."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from smc_desk.data.hashing import file_sha256

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V2.yaml"
DEFAULT_HASH_PATH = ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V2.sha256"
EXPECTED_SCHEMA = "smc_codex_market_structure_constitution_v2"
EXPECTED_VERSION = "2.0.0"
PROPOSED_STATUS = "PROPOSED_RESEARCH_DOCTRINE_NO_EXECUTION_AUTHORITY"


@dataclass(frozen=True)
class ConstitutionV2Proposal:
    schema: str
    version: str
    status: str
    event_ontology: tuple[str, ...]
    document: Mapping[str, Any]
    sha256: str
    path: Path

    @property
    def is_authoritative(self) -> bool:
        return False


def load_constitution_v2(
    path: str | Path = DEFAULT_PATH,
    hash_path: str | Path = DEFAULT_HASH_PATH,
) -> ConstitutionV2Proposal:
    source = Path(path)
    seal = Path(hash_path)
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("Constitution V2 must be a YAML mapping.")
    digest = file_sha256(source)
    if not seal.exists() or seal.read_text(encoding="utf-8").strip() != digest:
        raise ValueError("Constitution V2 hash mismatch or missing seal.")
    if document.get("schema") != EXPECTED_SCHEMA or document.get("version") != EXPECTED_VERSION:
        raise ValueError("Unexpected Constitution V2 schema or version.")
    if document.get("status") != PROPOSED_STATUS:
        raise ValueError("Constitution V2 loader accepts only the proposed non-authoritative status.")
    authority = document.get("authority_contract") or {}
    prohibited = (
        "signal_allowed",
        "paper_execution_allowed",
        "live_execution_allowed",
        "predictive_edge_claim_allowed",
    )
    if any(bool(authority.get(key)) for key in prohibited):
        raise ValueError("Constitution V2 proposal cannot grant signal, execution, or edge authority.")
    return ConstitutionV2Proposal(
        schema=str(document["schema"]),
        version=str(document["version"]),
        status=str(document["status"]),
        event_ontology=tuple(str(item) for item in document.get("event_ontology") or []),
        document=document,
        sha256=digest,
        path=source,
    )


__all__ = ["ConstitutionV2Proposal", "load_constitution_v2"]

