"""Tests for cross-run market-state memory and the narrative shadow artifact.

Both are additive, observe-only run-package evidence: the transition record
closes the memory loop that ``diff_states`` always supported but production
never persisted, and the shadow plan records the narrative planner's
compositional selection so the WP-SMC-13 analyst-marked cohort can measure it
against the canonical composer. Neither may fail a run, alter the sealed
evidence pack, or create signal authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from smc_desk.perception.market_state import build_market_state
from smc_desk.perception.market_state_memory import (
    STORE_SCHEMA,
    load_previous_state,
    market_state_from_dict,
    record_run_transition,
    save_current_state,
    store_path,
)
from tools.run_live_ai_smc_full_system import (
    _load_final_evidence_pack,
    write_colleague_memory_and_narrative_shadow,
)


def _pack_state(state: str = "POI_MAPPED", **overrides) -> dict:
    """A realistic market_state payload in evidence-pack (to_dict) form."""
    base = build_market_state(evidence_pack={}).to_dict()
    base.update(
        {
            "symbol": "BTCUSDT",
            "decision_time": "2026-08-10T12:00:00+00:00",
            "state": state,
            "waiting_for": "Price to travel toward the mapped POI.",
            "invalidation": "The bullish read fails if price body-closes beyond the 4h protected low.",
            "context": {"timeframe": "4h", "bias": "bullish", "narrative_state": "ALIGNED_CONTINUATION",
                        "price_location": "discount", "current_price": 64000.0},
            "liquidity": {"draw_price": 67255.0, "draw_kind": "unswept_liquidity",
                          "swept_ids": ["liq_1"], "unswept_ids": ["liq_2"]},
            "poi": {"primary_id": "poi_4h_ob_1", "primary_low": 63100.0, "primary_high": 63400.0,
                    "alternates": ["poi_4h_fvg_1"]},
        }
    )
    for key, value in overrides.items():
        base[key] = value
    return base


def test_market_state_from_dict_round_trips_real_pack_payload() -> None:
    payload = build_market_state(evidence_pack={}).to_dict()
    restored = market_state_from_dict(payload)
    assert restored.state == payload["state"]
    assert restored.bias == payload["context"]["bias"]
    assert restored.waiting_for == payload["waiting_for"]


def test_market_state_from_dict_restores_nested_groups() -> None:
    restored = market_state_from_dict(_pack_state())
    assert restored.state == "POI_MAPPED"
    assert restored.bias == "bullish"
    assert restored.primary_poi_id == "poi_4h_ob_1"
    assert restored.swept_liquidity_ids == ("liq_1",)
    assert restored.unswept_liquidity_ids == ("liq_2",)
    assert restored.current_price == 64000.0


def test_market_state_from_dict_tolerates_garbage() -> None:
    assert market_state_from_dict({}).state == "NO_CONTEXT"
    assert market_state_from_dict({"context": "not-a-mapping"}).bias == "unknown"


def test_first_observation_is_recorded_as_such(tmp_path: Path) -> None:
    record = record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=_pack_state())
    transition = record["transition"]
    assert transition["current_state"] == "POI_MAPPED"
    assert transition["advanced"] is True
    assert any("first" in note for note in record["notes"])
    assert record["signal_allowed"] is False


def test_second_run_detects_advance_and_newly_swept_liquidity(tmp_path: Path) -> None:
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=_pack_state("POI_MAPPED"))
    advanced = _pack_state(
        "TRADE_PLAN_READY",
        liquidity={"draw_price": 67255.0, "draw_kind": "unswept_liquidity",
                   "swept_ids": ["liq_1", "liq_9"], "unswept_ids": ["liq_2"]},
    )
    record = record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=advanced)
    transition = record["transition"]
    assert transition["previous_state"] == "POI_MAPPED"
    assert transition["advanced"] is True
    assert transition["regressed"] is False
    assert transition["newly_swept_liquidity"] == ["liq_9"]
    assert any("POI_MAPPED -> TRADE_PLAN_READY" in note for note in transition["notes"])


def test_bias_and_poi_changes_are_named(tmp_path: Path) -> None:
    record_run_transition(output_root=tmp_path, symbol="ETHUSDT", current_market_state=_pack_state())
    changed = _pack_state(
        context={"timeframe": "4h", "bias": "bearish", "narrative_state": "RETRACEMENT_WITHIN_PARENT",
                 "price_location": "premium", "current_price": 64100.0},
        poi={"primary_id": "poi_4h_ob_2", "primary_low": 65100.0, "primary_high": 65400.0, "alternates": []},
    )
    record = record_run_transition(output_root=tmp_path, symbol="ETHUSDT", current_market_state=changed)
    transition = record["transition"]
    assert transition["bias_changed"] is True
    assert transition["poi_changed"] is True
    assert any("bullish -> bearish" in note for note in transition["notes"])
    assert any("poi_4h_ob_1 -> poi_4h_ob_2" in note for note in transition["notes"])


def test_corrupt_store_is_fail_soft_and_recovers(tmp_path: Path) -> None:
    path = store_path(tmp_path, "SOLUSDT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    record = record_run_transition(output_root=tmp_path, symbol="SOLUSDT", current_market_state=_pack_state())
    assert any("unreadable" in note for note in record["notes"])
    assert record["transition"]["current_state"] == "POI_MAPPED"
    # The store self-heals: the current state is persisted after the failed read.
    restored, note = load_previous_state(path)
    assert restored is not None and restored.state == "POI_MAPPED" and note == ""


def test_store_envelope_is_atomic_and_schematised(tmp_path: Path) -> None:
    path = store_path(tmp_path, "BTCUSDT")
    save_current_state(path, _pack_state())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["schema"] == STORE_SCHEMA
    assert envelope["market_state"]["state"] == "POI_MAPPED"
    assert not path.with_suffix(".json.tmp").exists()
    assert path.name == "BTCUSDT.json" and path.parent.name == "market_state_store"


def _write_fake_run(symbol_root: Path, market_state: dict | None = None, run: int = 1) -> None:
    pack_dir = symbol_root / f"10_smc_evidence_pack_run_{run}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack = {
        "schema": "smc_evidence_pack",
        "symbol": symbol_root.name,
        "market_state": market_state if market_state is not None else _pack_state(),
        "formal_structure_graph": {
            "narrative_context": {"context_timeframe": "4h", "context_bias": "bullish",
                                  "state": "ALIGNED_CONTINUATION", "sentence": "4h bullish."},
            "active_range": {"range_id": "range_4h_1", "timeframe": "4h", "high": 66000.0,
                             "low": 63000.0, "price_location": "discount", "current_price": 64000.0},
        },
        "detector_candidates": {},
        "ohlcv_windows": {},
    }
    (pack_dir / "evidence_pack.json").write_text(json.dumps(pack), encoding="utf-8")


def test_load_final_evidence_pack_prefers_highest_run_number(tmp_path: Path) -> None:
    symbol_root = tmp_path / "BTCUSDT"
    _write_fake_run(symbol_root, run=1)
    _write_fake_run(symbol_root, run=2)
    # Poison the older pack so the wrong choice is visible.
    older = json.loads((symbol_root / "10_smc_evidence_pack_run_1" / "evidence_pack.json").read_text())
    older["marker"] = "old"
    (symbol_root / "10_smc_evidence_pack_run_1" / "evidence_pack.json").write_text(json.dumps(older))
    pack = _load_final_evidence_pack(symbol_root)
    assert pack is not None and pack.get("marker") != "old"


def test_load_final_evidence_pack_falls_back_to_base_folder(tmp_path: Path) -> None:
    symbol_root = tmp_path / "BTCUSDT"
    base_dir = symbol_root / "10_smc_evidence_pack"
    base_dir.mkdir(parents=True)
    (base_dir / "evidence_pack.json").write_text(json.dumps({"schema": "smc_evidence_pack"}))
    assert _load_final_evidence_pack(symbol_root) == {"schema": "smc_evidence_pack"}
    assert _load_final_evidence_pack(tmp_path / "MISSING") is None


def test_runner_helper_writes_memory_and_shadow_without_touching_canonical(tmp_path: Path) -> None:
    symbol_root = tmp_path / "run" / "BTCUSDT"
    _write_fake_run(symbol_root)
    canonical_dir = symbol_root / "14_clean_annotation_render"
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "annotation_plan_v2.json").write_text(json.dumps({"canonical": True}))

    outcome = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root, output_root=tmp_path, symbol="BTCUSDT"
    )
    assert outcome["memory_status"] == "recorded"
    assert outcome["shadow_status"] == "recorded"

    stage = symbol_root / "18_colleague_memory_narrative"
    transition = json.loads((stage / "market_state_transition.json").read_text())
    assert transition["signal_allowed"] is False
    assert transition["authority"] == "observe_only_colleague_memory"
    assert transition["transition"]["current_state"] == "POI_MAPPED"

    shadow = json.loads((stage / "narrative_annotation_plan_shadow.json").read_text())
    assert shadow["shadow_comparison_only"] is True
    assert shadow["rendered"] is False
    assert shadow["signal_allowed"] is False
    assert shadow["canonical_annotation_plan"] == "14_clean_annotation_render/annotation_plan_v2.json"
    assert isinstance(shadow["plan"]["selections"], list)
    # The range-first compositional read selected the dealing range.
    assert any(s.get("object_type") == "range_zone" for s in shadow["plan"]["selections"])

    # Canonical artifacts are byte-identical: nothing here writes outside 18_.
    assert json.loads((canonical_dir / "annotation_plan_v2.json").read_text()) == {"canonical": True}


def test_runner_helper_is_fail_soft_without_a_pack(tmp_path: Path) -> None:
    symbol_root = tmp_path / "run" / "ETHUSDT"
    symbol_root.mkdir(parents=True)
    outcome = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root, output_root=tmp_path, symbol="ETHUSDT"
    )
    assert outcome["memory_status"] == "evidence_pack_unavailable"
    assert outcome["shadow_status"] == "evidence_pack_unavailable"


def test_runner_helper_reports_when_pack_has_no_market_state(tmp_path: Path) -> None:
    symbol_root = tmp_path / "run" / "SOLUSDT"
    _write_fake_run(symbol_root, market_state={})
    outcome = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root, output_root=tmp_path, symbol="SOLUSDT"
    )
    assert outcome["memory_status"] == "no_market_state_in_pack"
    assert outcome["shadow_status"] == "recorded"

