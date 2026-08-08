from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from smc_desk.brain.agent_handoff.ai_seat_contract import (
    AI_SEAT_PROFILE_PATH,
    build_authority_bundle,
)
from smc_desk.brain.agent_handoff.export_agent_packet import export_agent_packet
from smc_desk.brain.agent_handoff.import_agent_response import (
    import_agent_response,
    verify_packet_integrity,
)


def _evidence_pack() -> dict:
    return {
        "schema": "smc_evidence_pack_v1",
        "symbol": "BTCUSDT",
        "decision_time": "2026-07-13T12:00:00+00:00",
        "ohlcv_windows": {
            "1d": [],
            "4h": [],
            "1h": [],
            "15m": [
                {"timestamp": "2026-07-13T11:30:00+00:00", "open": 62000.0, "high": 62100.0, "low": 61900.0, "close": 62050.0, "volume": 100.0},
                {"timestamp": "2026-07-13T11:45:00+00:00", "open": 62050.0, "high": 62200.0, "low": 62000.0, "close": 62150.0, "volume": 110.0},
            ],
        },
        "detector_candidates": {tf: {} for tf in ("1d", "4h", "1h", "15m")},
        "formal_structure_graph": {
            "schema": "formal_mtf_structure_graph_v1",
            "active_range": {"range_id": "range-4h-1", "high": 64000.0, "low": 61000.0},
            "invariants": {"status": "PASS"},
            "authority_contract": {"signal_allowed": False},
        },
        "formal_causal_episode_graph": {
            "schema": "formal_causal_episode_graph_v1",
            "invariants": {"status": "PASS"},
            "current_story": {"episode_id": "episode-4h-1"},
            "authority_contract": {"signal_allowed": False},
        },
        "authority_contract": {"signal_allowed": False, "execution": "disabled"},
    }


def _charts(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for timeframe in ("1d", "4h", "1h", "15m"):
        path = root / f"{timeframe}.png"
        Image.new("RGB", (32, 32), "white").save(path)
        result[timeframe] = path
    return result


def _packet(tmp_path: Path) -> tuple[Path, dict]:
    packet_dir = tmp_path / "packet"
    manifest = export_agent_packet(
        symbol="BTCUSDT",
        evidence_pack=_evidence_pack(),
        chart_paths=_charts(tmp_path),
        output_dir=packet_dir,
        decision_time="2026-07-13T12:00:00+00:00",
    )
    return packet_dir, manifest


def _response_from_packet(packet_dir: Path) -> dict:
    response = json.loads((packet_dir / "09_expected_output_schema.json").read_text(encoding="utf-8"))
    authority = json.loads((packet_dir / "00_authority_manifest.json").read_text(encoding="utf-8"))
    mirror_ids = authority["metamorphic_evidence"]["evidence_contract_ids"]
    response["agent_identity"] = {
        "agent_name": "Codex",
        "agent_model": "test-agent",
        "agent_version": "1",
        "review_started_at": "2026-07-13T12:01:00+00:00",
        "review_completed_at": "2026-07-13T12:02:00+00:00",
    }
    response["decision"]["symbol"] = "BTCUSDT"
    response["decision"]["setup_model"] = "observe_only_contract_test"
    response["decision"]["final_thesis"] = "Evidence-grounded watch state."
    for station in response["exam_transcript"]["stations"]:
        station["status"] = "PASS"
        station["summary"] = f"{station['station_id']} checked against sealed evidence."
        station["evidence_object_ids"] = ["range-4h-1"]
        if station["station_id"] == "S08_MECHANICAL_MIRROR" and mirror_ids:
            station["evidence_object_ids"].append(mirror_ids[0])
        station["doctrine_rule_ids"] = []
        station["resolution_condition"] = None
        if station["station_id"] == "S01_TIME_HONESTY":
            station["first_knowable_times"] = {"range-4h-1": "2026-07-13T08:00:00+00:00"}
    response["exam_transcript"]["declared_overall_status"] = "PASS"
    return response


def _write_response(root: Path, payload: dict) -> Path:
    response_dir = root / "response"
    response_dir.mkdir()
    (response_dir / "official_decision_candidate.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (response_dir / "agent_reasoning_summary.md").write_text(
        "Concise evidence summary; no private chain-of-thought.", encoding="utf-8"
    )
    return response_dir


def test_packet_v2_bundles_exact_hash_bound_authorities(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    verification = verify_packet_integrity(packet_dir)
    authority = json.loads((packet_dir / "00_authority_manifest.json").read_text(encoding="utf-8"))

    assert verification["legacy"] is False
    assert manifest["schema"] == "ai_smc_agent_packet_v2"
    assert manifest["sealed_input_hash"]
    assert authority["status"] == "PASS"
    assert authority["constitution"]["seal_matches"] is True
    assert authority["constitution"]["pending_count"] == 10
    assert authority["gauntlet"]["score_meaning"] == "protocol_conformance_not_perception_accuracy"
    assert (packet_dir / "00_AI_SEAT_PROFILE.md").read_bytes() == AI_SEAT_PROFILE_PATH.read_bytes()


def test_packet_tampering_is_fatal(tmp_path: Path) -> None:
    packet_dir, _ = _packet(tmp_path)
    profile = packet_dir / "00_AI_SEAT_PROFILE.md"
    profile.write_text(profile.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash_mismatch"):
        verify_packet_integrity(packet_dir)


def test_stale_constitution_seal_blocks_authority_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import smc_desk.brain.agent_handoff.ai_seat_contract as contract

    stale = tmp_path / "stale.sha256"
    stale.write_text("0" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(contract, "CONSTITUTION_SEAL_PATH", stale)

    bundle = build_authority_bundle(_evidence_pack())
    assert bundle["authority_manifest"]["status"] == "FATAL_AUTHORITY_VIOLATION"
    assert "constitution_seal_mismatch" in bundle["authority_manifest"]["violations"]


def test_complete_passing_exam_preserves_observe_only_decision(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response_dir = _write_response(tmp_path, _response_from_packet(packet_dir))

    imported = import_agent_response(
        response_dir,
        expected_packet_hash=manifest["sealed_input_hash"],
        packet_dir=packet_dir,
    )

    assert imported["decision"].official_state == "WATCH_ONLY"
    assert imported["exam_validation"]["status"] == "PASS_CONTRACT"
    assert imported["audit"]["packet_integrity_verified"] is True
    assert imported["audit"]["exam_downgrade_applied"] is False


def test_missing_exam_station_is_fatal(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    response["exam_transcript"]["stations"].pop()
    response_dir = _write_response(tmp_path, response)

    with pytest.raises(ValueError, match="missing_exam_station"):
        import_agent_response(
            response_dir,
            expected_packet_hash=manifest["sealed_input_hash"],
            packet_dir=packet_dir,
        )


def test_failed_exam_strips_trade_promotion_before_decision_parse(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    decision = response["decision"]
    decision["official_state"] = "TRADE_PLAN_READY"
    decision["direction"] = "bearish"
    decision["setup_grade"] = "A"
    decision["entry_plan"].update({"entry_ready": True, "entry_price": 63000.0})
    decision["stop_loss_plan"].update({"stop_price": 63500.0})
    decision["target_plan"]["targets"] = [{"price": 61500.0, "label": "SSL", "timeframe": "4h", "reason": "test"}]
    decision["rr_status"].update({"rr": 3.0, "pass_rr": True})
    decision["annotation_plan"].update({"chart_template": "trade_plan_chart", "show_trade_box": True})
    failed = next(item for item in response["exam_transcript"]["stations"] if item["station_id"] == "S04_BREAK_GRAMMAR")
    failed["status"] = "FAIL"
    failed["resolution_condition"] = "Provide an accepted break lifecycle with displacement and follow-through."
    response_dir = _write_response(tmp_path, response)

    imported = import_agent_response(
        response_dir,
        expected_packet_hash=manifest["sealed_input_hash"],
        packet_dir=packet_dir,
    )
    official = imported["decision"].to_official_dict()

    assert official["official_state"] == "REVIEW_REQUIRED"
    assert official["direction"] == "mixed"
    assert official["entry_plan"]["entry_ready"] is False
    assert official["entry_plan"]["entry_price"] is None
    assert official["stop_loss_plan"]["stop_price"] is None
    assert official["target_plan"]["targets"] == []
    assert official["rr_status"]["rr"] is None
    assert official["annotation_plan"]["show_trade_box"] is False
    assert official["annotation_plan"]["chart_template"] == "review_chart"
    assert imported["audit"]["exam_downgrade_applied"] is True


def test_response_packet_hash_substitution_is_fatal(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    response["packet_hash"] = "0" * 64
    response_dir = _write_response(tmp_path, response)

    with pytest.raises(ValueError, match="packet_hash"):
        import_agent_response(
            response_dir,
            expected_packet_hash=manifest["sealed_input_hash"],
            packet_dir=packet_dir,
        )


def test_exam_decision_time_substitution_is_fatal(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    response["exam_transcript"]["decision_time"] = "2026-07-14T12:00:00+00:00"
    response_dir = _write_response(tmp_path, response)

    with pytest.raises(ValueError, match="decision_time"):
        import_agent_response(
            response_dir,
            expected_packet_hash=manifest["sealed_input_hash"],
            packet_dir=packet_dir,
        )


def test_mirror_station_cannot_pass_without_mechanical_artifact(tmp_path: Path) -> None:
    evidence = _evidence_pack()
    evidence["ohlcv_windows"] = {"1d": [], "4h": [], "1h": [], "15m": []}
    packet_dir = tmp_path / "packet"
    manifest = export_agent_packet(
        symbol="BTCUSDT",
        evidence_pack=evidence,
        chart_paths=_charts(tmp_path),
        output_dir=packet_dir,
        decision_time="2026-07-13T12:00:00+00:00",
    )
    response_dir = _write_response(tmp_path, _response_from_packet(packet_dir))

    imported = import_agent_response(
        response_dir,
        expected_packet_hash=manifest["sealed_input_hash"],
        packet_dir=packet_dir,
    )

    assert imported["decision"].official_state == "REVIEW_REQUIRED"
    assert "S08_MECHANICAL_MIRROR" in imported["exam_validation"]["failed_stations"]
    station = imported["exam_validation"]["station_results"]["S08_MECHANICAL_MIRROR"]
    assert "mechanical_mirror_artifact_unavailable" in station["issues"]


def test_recorded_detector_dissent_forces_review_without_silent_substitution(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    response["dissent_records"] = [
        {
            "schema": "ai_seat_dissent_v1",
            "dissent_id": "dissent-1",
            "status": "PROPOSED_ALTERNATIVE",
            "claim": "The controlling break classification may be stale.",
            "proposed_interpretation": "Treat the event as a failed breakout candidate.",
            "evidence_object_ids": ["range-4h-1"],
            "resolution_condition": "Independent replay must resolve the controlling lifecycle.",
        }
    ]
    response_dir = _write_response(tmp_path, response)

    imported = import_agent_response(
        response_dir,
        expected_packet_hash=manifest["sealed_input_hash"],
        packet_dir=packet_dir,
    )

    assert imported["decision"].official_state == "REVIEW_REQUIRED"
    assert imported["unresolved_claim_validation"]["dissent_count"] == 1
    assert imported["audit"]["dissent_record_count"] == 1


def test_pending_doctrine_claim_must_name_a_real_pending_decision(tmp_path: Path) -> None:
    packet_dir, manifest = _packet(tmp_path)
    response = _response_from_packet(packet_dir)
    response["doctrine_pending_claims"] = [
        {
            "claim_id": "pending-1",
            "doctrine_decision_ids": ["invented_doctrine_decision"],
            "dependent_conclusion": "External break acceptance is unresolved.",
            "evidence_object_ids": ["range-4h-1"],
            "resolution_condition": "Ratify the threshold before promotion.",
        }
    ]
    response_dir = _write_response(tmp_path, response)

    imported = import_agent_response(
        response_dir,
        expected_packet_hash=manifest["sealed_input_hash"],
        packet_dir=packet_dir,
    )

    assert imported["decision"].official_state == "REVIEW_REQUIRED"
    issues = imported["unresolved_claim_validation"]["issues"]
    assert any(item["code"].endswith("unknown_decision_ids") for item in issues)
