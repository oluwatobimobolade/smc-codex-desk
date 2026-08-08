"""Canonical loader for the Market Structure Constitution.

Single source of truth: every perception module, AI role, and validator reads
doctrine from ``specs/MARKET_STRUCTURE_CONSTITUTION_V1.yaml`` through this
module. The YAML is the authoritative form; the loader exposes typed access and
verifies the integrity hash so no code silently operates against a mutated or
un-hashed doctrine.

Status of the Constitution is ``PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL``.
Until the human trader adjudicates the contested decisions, callers MUST NOT
treat any clause as authoritative -- see :func:`is_authoritative`.

WP-0044 / programme step 1 (Market Structure Constitution draft).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from smc_desk.data.hashing import file_sha256

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCTRINE_PATH = ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V1.yaml"
DEFAULT_HASH_PATH = ROOT / "specs" / "MARKET_STRUCTURE_CONSTITUTION_V1.sha256"
EXPECTED_SCHEMA = "smc_codex_market_structure_constitution_v1"
EXPECTED_VERSION = "1.0.0"
PROPOSED_STATUS = "PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL"
APPROVED_STATUS = "APPROVED_MARKET_STRUCTURE_CONSTITUTION_V1"

# Concepts whose definition is a decomposition rather than a structural object
# with a price-lifecycle. The programme's "every concept" field set
# (candidate_generation_rules, semantic_selection_rules, confirmation,
# invalidation) applies to structural objects; these are exempt by design.
DECOMPOSITION_CONCEPTS = frozenset({"confidence_and_abstention", "future_data_cutoff"})

STRUCTURAL_CONCEPT_FIELDS = (
    "formal_definition",
    "plain_definition",
    "candidate_generation_rules",
    "semantic_selection_rules",
    "confirmation",
    "invalidation",
    "lifecycle",
    "timeframe_ownership",
    "positive_example",
    "negative_example",
    "ambiguous_example",
    "unresolved_alternatives",
    "forbidden_shortcuts",
    "required_evidence",
    "optional_evidence",
)


@dataclass(frozen=True)
class ContestedDecision:
    id: str
    question: str
    proposed_default: str
    alternatives: tuple[str, ...]
    status: str
    rationale: str


@dataclass(frozen=True)
class DoctrineLoad:
    schema: str
    version: str
    status: str
    design_principles: tuple[Mapping[str, Any], ...]
    contested_decisions: tuple[ContestedDecision, ...]
    concepts: Mapping[str, Mapping[str, Any]]
    authority_and_provenance: Mapping[str, Any]
    doctrine_hash: str
    path: Path


def load_doctrine(
    path: Path | str = DEFAULT_DOCTRINE_PATH,
    hash_path: Path | str = DEFAULT_HASH_PATH,
) -> DoctrineLoad:
    """Load and integrity-check the Market Structure Constitution.

    Raises ``FileNotFoundError`` if the doctrine is absent and ``ValueError`` if
    the on-disk hash does not match the recomputed hash (tamper / drift).
    """
    p = Path(path)
    hp = Path(hash_path)
    if not p.exists():
        raise FileNotFoundError(f"Market Structure Constitution not found: {p}")
    if not hp.exists():
        raise FileNotFoundError(
            f"Market Structure Constitution hash is required and missing: {hp}"
        )
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(doc, Mapping):
        raise ValueError("Market Structure Constitution must be a YAML mapping.")
    doctrine_hash = file_sha256(p)
    recorded = hp.read_text(encoding="utf-8").strip()
    if not recorded:
        raise ValueError("Market Structure Constitution hash file is empty.")
    if recorded != doctrine_hash:
        raise ValueError(
            "Market Structure Constitution hash mismatch: on-disk "
            f"{recorded[:12]} != recomputed {doctrine_hash[:12]}. "
            "The doctrine YAML was changed without regenerating its hash."
        )
    if doc.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(f"Unexpected doctrine schema: {doc.get('schema')!r}")
    if doc.get("version") != EXPECTED_VERSION:
        raise ValueError(f"Unexpected doctrine version: {doc.get('version')!r}")
    ap = doc.get("authority_and_provenance", {})
    if not isinstance(ap, Mapping):
        raise ValueError("authority_and_provenance must be a mapping.")
    status = str(ap.get("status", ""))
    if status not in {PROPOSED_STATUS, APPROVED_STATUS}:
        raise ValueError(f"Unknown doctrine authority status: {status!r}")
    return DoctrineLoad(
        schema=doc.get("schema", ""),
        version=doc.get("version", ""),
        status=status,
        design_principles=tuple(doc.get("design_principles", [])),
        contested_decisions=tuple(
            ContestedDecision(
                id=str(d.get("id", "")),
                question=str(d.get("question", "")),
                proposed_default=str(d.get("proposed_default", "")),
                alternatives=tuple(d.get("alternatives", [])),
                status=str(d.get("status", "")),
                rationale=str(d.get("rationale", "")),
            )
            for d in doc.get("contested_decisions", [])
        ),
        concepts=doc.get("concepts", {}),
        authority_and_provenance=ap,
        doctrine_hash=doctrine_hash,
        path=p,
    )


@lru_cache(maxsize=1)
def doctrine() -> DoctrineLoad:
    """Process-wide cached doctrine load."""
    return load_doctrine()


def is_authoritative(load: DoctrineLoad | None = None) -> bool:
    """True only for the explicit approved status with no pending decisions.

    A PROPOSED doctrine may be read but never acted on as authoritative. The
    whole perception system must abstain on CERTIFIED outputs until this is
    True (programme §10, §17, §30).
    """
    if load is None:
        load = doctrine()
    return (
        load.status == APPROVED_STATUS
        and bool(load.contested_decisions)
        and all(d.status == "APPROVED" for d in load.contested_decisions)
    )


def unresolved_contested_decisions(load: DoctrineLoad | None = None) -> list[ContestedDecision]:
    """All contested decisions still marked PROPOSED (require human adjudication)."""
    if load is None:
        load = doctrine()
    return [d for d in load.contested_decisions if d.status != "APPROVED"]


def concept(name: str, load: DoctrineLoad | None = None) -> Mapping[str, Any]:
    """Return one concept's doctrine block, raising KeyError if absent."""
    if load is None:
        load = doctrine()
    return load.concepts[name]


def missing_structural_fields(name: str, load: DoctrineLoad | None = None) -> list[str]:
    """Structural-field completeness check (decomposition concepts exempt)."""
    if name in DECOMPOSITION_CONCEPTS:
        return []
    if load is None:
        load = doctrine()
    c = load.concepts.get(name)
    if c is None:
        return ["__missing_concept__"]
    return [f for f in STRUCTURAL_CONCEPT_FIELDS if f not in c]


__all__ = [
    "DEFAULT_DOCTRINE_PATH",
    "DEFAULT_HASH_PATH",
    "EXPECTED_SCHEMA",
    "EXPECTED_VERSION",
    "PROPOSED_STATUS",
    "APPROVED_STATUS",
    "DECOMPOSITION_CONCEPTS",
    "STRUCTURAL_CONCEPT_FIELDS",
    "ContestedDecision",
    "DoctrineLoad",
    "load_doctrine",
    "doctrine",
    "is_authoritative",
    "unresolved_contested_decisions",
    "concept",
    "missing_structural_fields",
]
