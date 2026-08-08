"""Immutable evidence geometry and derived display geometry for SMC markup."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


GEOMETRY_FIELDS = (
    "start_index",
    "end_index",
    "start_time",
    "end_time",
    "price",
    "price_low",
    "price_high",
)


def geometry_hash(geometry: Mapping[str, Any]) -> str:
    """Hash source geometry without trusting a caller-supplied hash."""
    payload = {
        key: value
        for key, value in geometry.items()
        if key != "geometry_hash"
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def geometry_values(source: Mapping[str, Any]) -> dict[str, Any]:
    return {key: source.get(key) for key in GEOMETRY_FIELDS}


def build_geometry_contract(
    *,
    evidence: Mapping[str, Any],
    display: Mapping[str, Any] | None = None,
    source_object_ids: Sequence[str] = (),
    anchor_mode: str = "exact_source",
    clipping_rule: str = "none",
) -> dict[str, dict[str, Any]]:
    """Build a reproducible two-geometry contract.

    Evidence geometry is immutable market/source truth. Display geometry may
    shorten only the horizontal presentation span; prices remain identical.
    """
    evidence_geometry = {
        **geometry_values(evidence),
        "source_object_ids": [str(value) for value in source_object_ids],
        "anchor_mode": anchor_mode,
        "immutable": True,
    }
    evidence_geometry["geometry_hash"] = geometry_hash(evidence_geometry)
    rendered = geometry_values(display or evidence)
    display_geometry = {
        **rendered,
        "clipping_rule": clipping_rule,
        "derived_from_evidence_hash": evidence_geometry["geometry_hash"],
    }
    return {
        "evidence_geometry": evidence_geometry,
        "display_geometry": display_geometry,
    }


def legacy_geometry_contract(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Load old decisions without silently certifying their provenance."""
    ids = [str(value) for value in raw.get("evidence_object_ids") or []]
    return build_geometry_contract(
        evidence=raw,
        source_object_ids=ids,
        anchor_mode="legacy_compatibility",
        clipping_rule="legacy_unverified",
    )


def effective_display_geometry(raw: Mapping[str, Any]) -> dict[str, Any]:
    display = raw.get("display_geometry")
    return geometry_values(display if isinstance(display, Mapping) else raw)


__all__ = [
    "GEOMETRY_FIELDS",
    "build_geometry_contract",
    "effective_display_geometry",
    "geometry_hash",
    "geometry_values",
    "legacy_geometry_contract",
]
