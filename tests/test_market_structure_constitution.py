"""Tests for the Market Structure Constitution (programme step 1).

Pins the doctrine contract:
  * YAML parses and is integrity-hashed (tamper detection).
  * All 14 contested decisions are present and marked PROPOSED with a
    proposed default and at least one alternative (no silent resolution).
  * Every structural concept carries the full field set the programme §10
    requires (decomposition concepts are exempt by design).
  * The loader refuses to act authoritatively while the doctrine is PROPOSED.
  * The doctrine hash is reproducible.

Run with::

    PYTHONPATH=. pytest tests/test_market_structure_constitution.py -v
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from smc_desk.structure.doctrine import (
    DEFAULT_DOCTRINE_PATH,
    DEFAULT_HASH_PATH,
    DECOMPOSITION_CONCEPTS,
    STRUCTURAL_CONCEPT_FIELDS,
    is_authoritative,
    load_doctrine,
    missing_structural_fields,
    unresolved_contested_decisions,
)

REQUIRED_CONCEPTS = {
    "swing", "protected_point", "bos", "choch", "mss", "sweep", "breakout",
    "probe", "reclaim", "active_range", "liquidity", "poi", "inducement",
    "displacement", "confidence_and_abstention", "future_data_cutoff",
}


@pytest.fixture(scope="module")
def doctrine():
    return load_doctrine()


def test_doctrine_parses_and_hashes_match() -> None:
    load = load_doctrine()
    expected = hashlib.sha256(Path(DEFAULT_DOCTRINE_PATH).read_bytes()).hexdigest()
    assert load.doctrine_hash == expected
    if Path(DEFAULT_HASH_PATH).exists():
        recorded = Path(DEFAULT_HASH_PATH).read_text().strip()
        assert recorded == expected, "on-disk doctrine hash is stale"


def test_schema_and_version(doctrine) -> None:
    assert doctrine.schema == "smc_codex_market_structure_constitution_v1"
    assert doctrine.version == "1.0.0"
    assert doctrine.status == "PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL"


def test_all_required_concepts_present(doctrine) -> None:
    assert set(doctrine.concepts) == REQUIRED_CONCEPTS


def test_every_structural_concept_has_full_field_set(doctrine) -> None:
    problems = {}
    for name in doctrine.concepts:
        miss = missing_structural_fields(name, doctrine)
        if miss:
            problems[name] = miss
    assert problems == {}, f"concepts missing required fields: {problems}"


def test_decomposition_concepts_exempt_and_defined(doctrine) -> None:
    for name in DECOMPOSITION_CONCEPTS:
        assert name in doctrine.concepts
    ca = doctrine.concepts["confidence_and_abstention"]
    axes = ca.get("confidence_axes", [])
    cats = ca.get("categories", [])
    # axes/categories are stored as lists of single-key mappings
    assert isinstance(axes, list) and len(axes) == 6, f"expected 6 confidence axes, got {axes}"
    assert isinstance(cats, list) and len(cats) == 5, f"expected 5 categories, got {cats}"
    axis_keys = {next(iter(a)) for a in axes if isinstance(a, dict)}
    assert axis_keys == {
        "data_confidence", "geometry_confidence", "doctrine_confidence",
        "ai_agreement", "critic_confidence", "human_agreement_estimate",
    }
    cat_keys = {next(iter(c)) for c in cats if isinstance(c, dict)}
    assert cat_keys == {
        "confirmed", "probable", "ambiguous", "contradicted", "insufficient_context",
    }
    assert ca.get("abstention_rule")


def test_all_14_contested_decisions_are_proposed(doctrine) -> None:
    assert len(doctrine.contested_decisions) == 14
    for d in doctrine.contested_decisions:
        assert d.status == "PROPOSED", f"{d.id} not PROPOSED"
        assert d.proposed_default, f"{d.id} has no proposed default"
        assert d.alternatives, f"{d.id} has no alternatives"


def test_protected_point_forbids_current_shortcut(doctrine) -> None:
    """The Constitution must explicitly reject the current implementation's bug."""
    pp = doctrine.concepts["protected_point"]
    forbidden = " ".join(pp.get("forbidden_shortcuts", []))
    assert "track.protected_low = track.last_confirmed_low" in forbidden
    assert "last_confirmed_low" in forbidden


def test_poi_forbids_nearest_candle_shortcut(doctrine) -> None:
    poi = doctrine.concepts["poi"]
    forbidden = " ".join(poi.get("forbidden_shortcuts", []))
    assert "nearest opposing candle" in forbidden


def test_anchor_preservation_principle_present(doctrine) -> None:
    ids = {p.get("id") for p in doctrine.design_principles}
    assert "anchor_preservation" in ids


def test_doctrine_is_not_authoritative_while_proposed(doctrine) -> None:
    assert is_authoritative(doctrine) is False
    assert len(unresolved_contested_decisions(doctrine)) == 14


def test_forbidden_shortcuts_present_on_all_structural_concepts(doctrine) -> None:
    for name in doctrine.concepts:
        if name in DECOMPOSITION_CONCEPTS:
            continue
        fs = doctrine.concepts[name].get("forbidden_shortcuts")
        assert fs, f"{name} has no forbidden_shortcuts"


def test_loader_detects_hash_tamper(tmp_path: Path) -> None:
    import shutil
    src = Path(DEFAULT_DOCTRINE_PATH)
    copy = tmp_path / "tampered.yaml"
    shutil.copy(src, copy)
    text = copy.read_text(encoding="utf-8")
    text = text.replace(
        "PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL",
        "PROPOSED_DOCTRINE_DRAFT_PENDING_HUMAN_APPROVAL_X",
    )
    copy.write_text(text, encoding="utf-8")
    # feed the real (correct) hash so the loader sees a mismatch
    bad_hash_path = tmp_path / "tampered.sha256"
    bad_hash_path.write_text(hashlib.sha256(src.read_bytes()).hexdigest() + "\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_doctrine(copy, bad_hash_path)