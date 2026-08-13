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
import multiprocessing
from pathlib import Path

import pytest
import smc_desk.perception.market_state_memory as memory_module
from smc_desk.perception.market_state import build_market_state
from smc_desk.perception.market_state_memory import (
    STORE_SCHEMA,
    load_previous_state,
    market_identity_hash,
    market_state_from_dict,
    normalize_market_identity,
    record_run_transition,
    save_current_state,
    store_path,
)
from tools.run_live_ai_smc_full_system import (
    _compare_shadow_to_canonical,
    _load_final_evidence_pack,
    _market_identity_from_pack,
    _narrative_draw_note,
    _perception_failures,
    _with_narrative_draw,
    render_summary_markdown,
    write_colleague_memory_and_narrative_shadow,
)


def _pack_state(
    state: str = "POI_MAPPED",
    *,
    symbol: str = "BTCUSDT",
    decision_time: str = "2026-08-10T12:00:00+00:00",
    **overrides,
) -> dict:
    """A realistic market_state payload in evidence-pack (to_dict) form."""
    base = build_market_state(evidence_pack={}).to_dict()
    base.update(
        {
            "symbol": symbol,
            "decision_time": decision_time,
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


def _concurrent_record_worker(
    output_root: str,
    start_event,
    state: str,
    decision_time: str,
) -> None:
    start_event.wait()
    record_run_transition(
        output_root=output_root,
        symbol="ETHUSDT",
        current_market_state=_pack_state(
            state,
            symbol="ETHUSDT",
            decision_time=decision_time,
        ),
    )


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
        decision_time="2026-08-10T13:00:00+00:00",
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
    record_run_transition(
        output_root=tmp_path,
        symbol="ETHUSDT",
        current_market_state=_pack_state(symbol="ETHUSDT"),
    )
    changed = _pack_state(
        symbol="ETHUSDT",
        decision_time="2026-08-10T13:00:00+00:00",
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
    record = record_run_transition(
        output_root=tmp_path,
        symbol="SOLUSDT",
        current_market_state=_pack_state(symbol="SOLUSDT"),
    )
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
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    assert path.name == "BTCUSDT.json" and path.parent.name == "market_state_store"


def _write_fake_run(symbol_root: Path, market_state: dict | None = None, run: int = 1) -> None:
    pack_dir = symbol_root / f"10_smc_evidence_pack_run_{run}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack = {
        "schema": "smc_evidence_pack",
        "symbol": symbol_root.name,
        "market_state": market_state if market_state is not None else _pack_state(symbol=symbol_root.name),
        "formal_structure_graph": {
            "narrative_context": {"context_timeframe": "4h", "context_bias": "bullish",
                                  "state": "ALIGNED_CONTINUATION", "sentence": "4h bullish."},
            "active_range": {"range_id": "range_4h_1", "timeframe": "4h", "high": 66000.0,
                             "low": 63000.0, "price_location": "discount", "current_price": 64000.0},
        },
        "detector_candidates": {},
        "ohlcv_windows": {},
        "session_context": {
            "source_manifest": {
                "source": "test_exchange_rest",
                "symbol": symbol_root.name,
                "provider_symbol": symbol_root.name,
                "market_type": "test perpetual",
                "timeframes": {"15m": {}, "1h": {}, "4h": {}, "1d": {}},
            }
        },
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
    assert outcome["memory_status"] == "created"
    assert outcome["memory_store_updated"] is True
    assert outcome["memory_forward_transition"] is True
    assert outcome["shadow_status"] == "recorded"

    stage = symbol_root / "18_colleague_memory_narrative"
    transition = json.loads((stage / "market_state_transition.json").read_text())
    assert transition["signal_allowed"] is False
    assert transition["authority"] == "observe_only_colleague_memory"
    assert transition["transition"]["current_state"] == "POI_MAPPED"

    shadow = json.loads((stage / "narrative_annotation_plan_shadow.json").read_text())
    assert shadow["schema"] == "narrative_annotation_plan_shadow_v2"
    assert shadow["shadow_comparison_only"] is True
    assert shadow["rendered"] is False
    assert shadow["signal_allowed"] is False
    assert shadow["canonical_annotation_plan"] == "14_clean_annotation_render/annotation_plan_v2.json"
    assert isinstance(shadow["plan"]["selections"], list)
    assert shadow["comparison"]["promotion_eligible"] is False
    assert shadow["comparison"]["human_review_status"] == "NOT_SCORED"
    assert shadow["provenance"]["evidence_pack_sha256"]
    assert shadow["provenance"]["canonical_annotation_plan_sha256"]
    assert outcome["shadow_comparison_metrics"]["promotion_eligible"] is False
    # The range-first compositional read selected the dealing range.
    assert any(s.get("object_type") == "range_zone" for s in shadow["plan"]["selections"])

    # Canonical artifacts are byte-identical: nothing here writes outside 18_.
    assert json.loads((canonical_dir / "annotation_plan_v2.json").read_text()) == {"canonical": True}


def test_runner_helper_surfaces_store_conflict_notes_and_preserves_memory(tmp_path: Path) -> None:
    symbol_root = tmp_path / "run" / "BTCUSDT"
    _write_fake_run(symbol_root, market_state=_pack_state("TRADE_PLAN_READY"))
    first = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root,
        output_root=tmp_path,
        symbol="BTCUSDT",
    )
    assert first["memory_status"] == "created"

    pack_path = symbol_root / "10_smc_evidence_pack_run_1" / "evidence_pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["market_state"] = _pack_state("NO_CONTEXT")
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    second = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root,
        output_root=tmp_path,
        symbol="BTCUSDT",
    )
    assert second["memory_status"] == "preserved_equal_time_conflict"
    assert second["memory_store_updated"] is False
    assert second["memory_forward_transition"] is False
    assert any("conflicting state or evidence" in note for note in second["transition_notes"])

    identity = second["market_identity"]
    stored, _ = load_previous_state(store_path(tmp_path, "BTCUSDT", identity))
    assert stored is not None and stored.state == "TRADE_PLAN_READY"


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



def test_out_of_order_replay_is_flagged_and_does_not_update_store(tmp_path: Path) -> None:
    newer = _pack_state("TRADE_PLAN_READY", decision_time="2026-08-10T12:00:00+00:00")
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=newer)

    older = _pack_state("POI_MAPPED", decision_time="2026-08-09T12:00:00+00:00")
    record = record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=older)

    assert record["forward_transition"] is False
    assert record["store_status"] == "preserved_newer_state"
    assert record["store_updated"] is False
    assert record["previous_decision_time"] == "2026-08-10T12:00:00+00:00"
    assert record["current_decision_time"] == "2026-08-09T12:00:00+00:00"
    assert any("LATER decision time" in note for note in record["notes"])
    # The store must still hold the newer state: a replay never poisons memory.
    stored, note = load_previous_state(store_path(tmp_path, "BTCUSDT"))
    assert stored is not None and stored.decision_time == "2026-08-10T12:00:00+00:00"
    assert stored.state == "TRADE_PLAN_READY"


def test_forward_run_updates_store(tmp_path: Path) -> None:
    older = _pack_state("POI_MAPPED", decision_time="2026-08-10T12:00:00+00:00")
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=older)
    newer = _pack_state("PRICE_AT_POI", decision_time="2026-08-10T13:00:00+00:00")
    record = record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=newer)
    assert record["forward_transition"] is True
    assert record["store_status"] == "updated"
    assert record["store_updated"] is True
    assert record["transition"]["advanced"] is True
    stored, _ = load_previous_state(store_path(tmp_path, "BTCUSDT"))
    assert stored is not None and stored.state == "PRICE_AT_POI"


def test_equal_decision_time_rerun_is_a_forward_reobservation(tmp_path: Path) -> None:
    state = _pack_state(decision_time="2026-08-10T12:00:00+00:00")
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=state)
    record = record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=state)
    assert record["forward_transition"] is True
    assert record["store_status"] == "reobserved_equal_unchanged"
    assert record["store_updated"] is False
    assert record["transition"]["advanced"] is False
    assert record["transition"]["regressed"] is False


def test_unverifiable_current_time_is_disclosed_and_cannot_poison_store(tmp_path: Path) -> None:
    trusted = _pack_state("TRADE_PLAN_READY", decision_time="2026-08-10T12:00:00+00:00")
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=trusted)
    record = record_run_transition(
        output_root=tmp_path,
        symbol="BTCUSDT",
        current_market_state=_pack_state("NO_CONTEXT", decision_time="not-a-timestamp"),
    )
    assert record["forward_transition"] is False
    assert record["store_updated"] is False
    assert record["store_status"] == "preserved_unverifiable_current_time"
    assert any("unparseable" in note and "NOT updated" in note for note in record["notes"])
    stored, _ = load_previous_state(store_path(tmp_path, "BTCUSDT"))
    assert stored is not None and stored.state == "TRADE_PLAN_READY"
    assert stored.decision_time == "2026-08-10T12:00:00+00:00"


def test_equal_time_conflict_is_descriptive_and_preserves_trusted_store(tmp_path: Path) -> None:
    trusted = _pack_state("TRADE_PLAN_READY")
    record_run_transition(output_root=tmp_path, symbol="BTCUSDT", current_market_state=trusted)
    record = record_run_transition(
        output_root=tmp_path,
        symbol="BTCUSDT",
        current_market_state=_pack_state("NO_CONTEXT"),
    )
    assert record["forward_transition"] is False
    assert record["store_updated"] is False
    assert record["store_status"] == "preserved_equal_time_conflict"
    stored, _ = load_previous_state(store_path(tmp_path, "BTCUSDT"))
    assert stored is not None and stored.state == "TRADE_PLAN_READY"


def test_source_bound_identity_separates_same_symbol_markets(tmp_path: Path) -> None:
    futures = normalize_market_identity(
        "XAUUSD",
        {
            "source": "yahoo_chart",
            "provider_symbol": "GC=F",
            "market_type": "COMEX gold futures proxy",
            "timeframe_profile": ["15m", "1h", "4h", "1d"],
        },
    )
    spot = normalize_market_identity(
        "XAUUSD",
        {
            "source": "oanda_rest",
            "provider_symbol": "XAU_USD",
            "market_type": "spot CFD",
            "timeframe_profile": ["15m", "1h", "4h", "1d"],
        },
    )
    futures_path = store_path(tmp_path, "XAUUSD", futures)
    spot_path = store_path(tmp_path, "XAUUSD", spot)
    assert futures_path != spot_path
    assert market_identity_hash(futures) != market_identity_hash(spot)

    first = record_run_transition(
        output_root=tmp_path,
        symbol="XAUUSD",
        current_market_state=_pack_state(symbol="XAUUSD"),
        market_identity=futures,
        evidence_fingerprint="futures-pack",
    )
    second = record_run_transition(
        output_root=tmp_path,
        symbol="XAUUSD",
        current_market_state=_pack_state(symbol="XAUUSD"),
        market_identity=spot,
        evidence_fingerprint="spot-pack",
    )
    assert first["store_status"] == second["store_status"] == "created"
    assert futures_path.exists() and spot_path.exists()


def test_current_symbol_mismatch_never_updates_store(tmp_path: Path) -> None:
    record = record_run_transition(
        output_root=tmp_path,
        symbol="ETHUSDT",
        current_market_state=_pack_state(symbol="BTCUSDT"),
    )
    assert record["store_status"] == "rejected_current_symbol_mismatch"
    assert record["store_updated"] is False
    assert not store_path(tmp_path, "ETHUSDT").exists()


def test_unknown_store_schema_is_preserved_fail_closed(tmp_path: Path) -> None:
    path = store_path(tmp_path, "BTCUSDT")
    path.parent.mkdir(parents=True)
    original = {
        "schema": "market_state_memory_store_v999",
        "market_state": _pack_state("TRADE_PLAN_READY"),
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    record = record_run_transition(
        output_root=tmp_path,
        symbol="BTCUSDT",
        current_market_state=_pack_state("NO_CONTEXT", decision_time="2026-08-10T13:00:00Z"),
    )
    assert record["store_status"] == "preserved_unsupported_schema"
    assert record["store_updated"] is False
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_save_failure_is_truthfully_reported_without_claiming_recorded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_save(*args, **kwargs) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(memory_module, "save_current_state", fail_save)
    record = record_run_transition(
        output_root=tmp_path,
        symbol="BTCUSDT",
        current_market_state=_pack_state(),
    )
    assert record["store_status"] == "save_or_lock_failed"
    assert record["store_updated"] is False
    assert record["forward_transition"] is False
    assert any("not stored" in note for note in record["notes"])
    assert not store_path(tmp_path, "BTCUSDT").exists()


def test_concurrent_writers_cannot_regress_the_store(tmp_path: Path) -> None:
    try:
        context = multiprocessing.get_context("spawn")
    except ValueError:  # pragma: no cover - supported Python runtimes provide spawn
        pytest.skip("multiprocessing spawn context required for the lock test")
    start = context.Event()
    older = context.Process(
        target=_concurrent_record_worker,
        args=(str(tmp_path), start, "POI_MAPPED", "2026-08-11T12:00:00Z"),
    )
    newer = context.Process(
        target=_concurrent_record_worker,
        args=(str(tmp_path), start, "TRADE_PLAN_READY", "2026-08-11T13:00:00Z"),
    )
    older.start()
    newer.start()
    start.set()
    older.join(10)
    newer.join(10)
    assert older.exitcode == newer.exitcode == 0
    stored, note = load_previous_state(store_path(tmp_path, "ETHUSDT"))
    assert note == ""
    assert stored is not None and stored.state == "TRADE_PLAN_READY"
    assert stored.decision_time == "2026-08-11T13:00:00Z"



def _pack_with_draw_and_failures() -> dict:
    return {
        "formal_structure_graph": {
            "narrative_context": {
                "state": "ALIGNED_CONTINUATION",
                "draw": {"direction": "bearish", "target_price": 1820.61,
                         "target_kind": "equal_lows", "rationale": "nearest unswept"},
            }
        },
        "session_context": {
            "perception_candidates": {
                "timeframes": {
                    "15m": {"status": "FAILED", "error_type": "ValueError",
                            "error": "Cannot analyze sequence containing gaps or incomplete data"},
                    "1h": {"status": "PASS", "candidate_counts": {}},
                    "4h": {"status": "PASS", "candidate_counts": {}},
                    "1d": {"status": "PASS", "candidate_counts": {}},
                }
            }
        },
    }


def test_narrative_draw_note_names_the_draw_descriptively() -> None:
    note = _narrative_draw_note(_pack_with_draw_and_failures())
    assert "bearish" in note
    assert "1,820.6" in note
    assert "equal lows" in note
    assert "unpromoted" in note and "not a validated sweep target" in note


def test_narrative_draw_note_is_silent_without_a_valid_draw() -> None:
    assert _narrative_draw_note({}) == ""
    assert _narrative_draw_note({"formal_structure_graph": {"narrative_context": {"draw": {}}}}) == ""
    bad = _pack_with_draw_and_failures()
    bad["formal_structure_graph"]["narrative_context"]["draw"]["direction"] = "sideways"
    assert _narrative_draw_note(bad) == ""
    bad2 = _pack_with_draw_and_failures()
    bad2["formal_structure_graph"]["narrative_context"]["draw"]["target_price"] = "n/a"
    assert _narrative_draw_note(bad2) == ""


def test_draw_is_appended_even_when_base_narrative_already_has_an_active_poi() -> None:
    narrative = _with_narrative_draw(
        "A confirmed active POI is mapped for observation.",
        _pack_with_draw_and_failures(),
    )
    assert "active POI" in narrative
    assert "standing draw" in narrative
    assert "not a validated sweep target" in narrative


def test_perception_failures_are_surfaced_in_timeframe_order() -> None:
    failures = _perception_failures(_pack_with_draw_and_failures())
    assert failures == ["15m: ValueError - Cannot analyze sequence containing gaps or incomplete data"]


def test_perception_failures_empty_when_all_pass() -> None:
    pack = _pack_with_draw_and_failures()
    pack["session_context"]["perception_candidates"]["timeframes"]["15m"] = {"status": "PASS"}
    assert _perception_failures(pack) == []
    assert _perception_failures({}) == []


def test_runner_helper_reports_perception_failures(tmp_path: Path) -> None:
    symbol_root = tmp_path / "run" / "XAUUSD"
    pack_dir = symbol_root / "10_smc_evidence_pack_run_1"
    pack_dir.mkdir(parents=True)
    pack = _pack_with_draw_and_failures()
    pack["market_state"] = _pack_state(symbol="XAUUSD")
    (pack_dir / "evidence_pack.json").write_text(json.dumps(pack), encoding="utf-8")
    outcome = write_colleague_memory_and_narrative_shadow(
        symbol_root=symbol_root, output_root=tmp_path, symbol="XAUUSD"
    )
    assert outcome["perception_failures"] == [
        "15m: ValueError - Cannot analyze sequence containing gaps or incomplete data"
    ]


def test_shadow_comparison_measures_overlap_and_blocks_promotion() -> None:
    shadow_plan = {
        "selections": [
            {
                "semantic_object_id": "ob_1",
                "object_type": "poi_zone",
                "timeframe": "4h",
                "label": "4H Demand OB",
            },
            {
                "semantic_object_id": "bos_2",
                "object_type": "structure_segment",
                "timeframe": "1h",
                "label": "1H BOS",
            },
        ]
    }
    canonical = {
        "objects": [
            {
                "semantic_object_id": "ob_1:poi_zone",
                "evidence_object_ids": ["ob_1"],
                "object_type": "poi_zone",
                "timeframe": "4h",
            }
        ]
    }
    pack = {
        "market_state": {
            "state": "POI_MAPPED",
            "context": {"narrative_state": "ALIGNED_CONTINUATION"},
            "reasons": [],
        }
    }
    comparison = _compare_shadow_to_canonical(
        shadow_plan=shadow_plan,
        canonical_plan=canonical,
        evidence_pack=pack,
        official_decision={"official_state": "WATCH_ONLY"},
    )
    assert comparison["matched_count"] == 1
    assert comparison["shadow_count"] == 2
    assert comparison["canonical_count"] == 1
    assert comparison["shadow_precision"] == 0.5
    assert comparison["canonical_recall"] == 1.0
    assert comparison["promotion_eligible"] is False
    assert comparison["human_cohort_score_required"] is True


def test_shadow_comparison_flags_reconciliation_conflict() -> None:
    comparison = _compare_shadow_to_canonical(
        shadow_plan={
            "selections": [
                {
                    "semantic_object_id": "ob_1",
                    "object_type": "poi_zone",
                    "timeframe": "4h",
                }
            ]
        },
        canonical_plan={"objects": []},
        evidence_pack={
            "market_state": {
                "state": "NO_CONTEXT",
                "context": {"narrative_state": "RECONCILIATION_REQUIRED"},
                "reasons": ["causal episode reconciliation required"],
            }
        },
        official_decision={"official_state": "REVIEW_REQUIRED"},
    )
    assert comparison["status"] == "RECONCILIATION_CONFLICT_REVIEW_REQUIRED"
    assert comparison["reconciliation_required"] is True
    assert comparison["promotion_eligible"] is False


def test_market_identity_extraction_excludes_dynamic_manifest_fields() -> None:
    pack = {
        "session_context": {
            "source_manifest": {
                "source": "yahoo_chart",
                "symbol": "XAUUSD",
                "provider_symbol": "GC=F",
                "market_type": "COMEX gold futures proxy",
                "timeframes": {"15m": {"last_timestamp": "later"}, "1h": {}},
            }
        }
    }
    identity = _market_identity_from_pack(pack, "XAUUSD")
    assert identity == {
        "canonical_symbol": "XAUUSD",
        "source": "yahoo_chart",
        "provider_symbol": "GC=F",
        "market_type": "comex gold futures proxy",
        "timeframe_profile": ["15m", "1h"],
    }


def test_summary_markdown_discloses_memory_source_gaps_and_shadow_metrics() -> None:
    markdown = render_summary_markdown(
        {
            "created_at": "2026-08-11T12:00:00Z",
            "run_dir": "/tmp/run",
            "results": [
                {
                    "symbol": "XAUUSD",
                    "status": "REVIEW_REQUIRED",
                    "official_state": "REVIEW_REQUIRED",
                    "validation_result": "REVIEW_REQUIRED",
                    "output_dir": "/tmp/run/XAUUSD",
                    "official_chart": "/tmp/chart.png",
                    "thesis_path": "/tmp/thesis.md",
                    "colleague_memory": "preserved_unverifiable_current_time",
                    "memory_store_updated": False,
                    "memory_forward_transition": False,
                    "memory_market_identity": {
                        "source": "yahoo_chart",
                        "provider_symbol": "GC=F",
                        "market_type": "comex gold futures proxy",
                    },
                    "narrative_shadow_comparison": "RECONCILIATION_CONFLICT_REVIEW_REQUIRED",
                    "narrative_shadow_metrics": {
                        "matched_count": 0,
                        "shadow_count": 6,
                        "canonical_count": 1,
                        "human_review_status": "NOT_SCORED",
                        "promotion_eligible": False,
                    },
                    "memory_transition_notes": [
                        "current time unparseable; store was NOT updated"
                    ],
                    "perception_failures": ["15m: ValueError - gaps"],
                    "last_prices": {"15m": 4400.0},
                    "source_manifest": {},
                    "hard_issues": [],
                }
            ],
        }
    )
    assert "preserved_unverifiable_current_time" in markdown
    assert "store updated: `false`" in markdown
    assert "yahoo_chart / GC=F" in markdown
    assert "0` matched of `6" in markdown
    assert "store was NOT updated" in markdown
    assert "Perception gaps" in markdown
