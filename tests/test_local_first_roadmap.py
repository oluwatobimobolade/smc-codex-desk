from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.evaluation.adjudication import AnnotatorSubmission, compute_inter_annotator_agreement
from smc_desk.evaluation.holdout_guard import HoldoutViolation, assert_not_in_holdout
from tools.build_desktop_ai_review_packet import build_packets
from tools.export_adjudication_dataset import build_rows
from tools.measure_review_agreement import build_agreement_report
from tools.sync_market_data import build_manifest


def _write_ohlcv(path: Path, periods: int = 8) -> None:
    timestamps = pd.date_range("2026-01-01", periods=periods, freq="15min", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": [ts.isoformat() for ts in timestamps],
            "open": [100.0 + i for i in range(periods)],
            "high": [101.0 + i for i in range(periods)],
            "low": [99.0 + i for i in range(periods)],
            "close": [100.5 + i for i in range(periods)],
            "volume": [1000.0] * periods,
        }
    ).to_csv(path, index=False)


def test_holdout_guard_blocks_overlapping_research_window(tmp_path: Path) -> None:
    policy = tmp_path / "holdout.json"
    policy.write_text(
        json.dumps(
            {
                "windows": [
                    {
                        "name": "locked",
                        "start": "2026-01-10T00:00:00Z",
                        "end": "2026-01-20T00:00:00Z",
                        "symbols": ["BTCUSDT"],
                        "actions": ["case_generation"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HoldoutViolation):
        assert_not_in_holdout(
            start="2026-01-09T00:00:00Z",
            end="2026-01-11T00:00:00Z",
            symbol="BTCUSDT",
            action="case_generation",
            policy_path=policy,
        )

    matches = assert_not_in_holdout(
        start="2026-01-09T00:00:00Z",
        end="2026-01-11T00:00:00Z",
        symbol="BTCUSDT",
        action="case_generation",
        policy_path=policy,
        allow_holdout=True,
    )
    assert [match.name for match in matches] == ["locked"]


def test_sync_market_data_manifest_marks_clean_local_csv_pass(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    symbol_dir = data_root / "BTCUSDT"
    symbol_dir.mkdir(parents=True)
    _write_ohlcv(symbol_dir / "BTCUSDT_15m_unit.csv")
    args = Namespace(
        data_root=str(data_root),
        symbols=["BTCUSDT"],
        intervals=["15m"],
        tag="unit",
        refresh=False,
        derive_htf="off",
        holdout_policy=str(tmp_path / "missing_policy.json"),
    )

    manifest = build_manifest(args, refresh_result=None, derive_results=[])

    assert manifest["verdict"] == "PASS"
    assert manifest["canonical_contract"]["canonical_timeframe"] == "15m"
    assert manifest["files"][0]["sha256"]
    assert manifest["files"][0]["clean_for_research"] is True


def test_adjudication_clusters_agreed_and_disputed_objects() -> None:
    shared = {"direction": "bullish", "timestamp": "2026-01-01T12:00:00Z", "price": 100.0}
    submissions = [
        AnnotatorSubmission(case_id="CASE-001", annotator_id="rev_a", proposed_objects={"bos": [shared]}),
        AnnotatorSubmission(
            case_id="CASE-001",
            annotator_id="rev_b",
            proposed_objects={
                "bos": [
                    dict(shared, price=100.02),
                    {"direction": "bearish", "timestamp": "2026-01-01T14:00:00Z", "price": 90.0},
                ]
            },
        ),
    ]

    result = compute_inter_annotator_agreement(submissions)["CASE-001:bos"]

    assert len(result.agreed_objects) == 1
    assert len(result.disputed_objects) == 1
    assert result.agreement_rate == 0.5
    assert result.agreed_objects[0]["supporting_annotators"] == ["rev_a", "rev_b"]


def _annotation_payload(*, status: str, reviewer_ids: list[str], adjudicated_by: str | None = None) -> dict:
    payload = {
        "schema_version": "1.0",
        "label_status": status,
        "reviewer_ids": reviewer_ids,
        "adjudicated_by": adjudicated_by,
        "objects": [
            {
                "annotation_id": f"{reviewer_ids[0] if reviewer_ids else 'adj'}-bos-1",
                "primitive": "bos",
                "timeframe": "15m",
                "direction": "bullish",
                "structure_scope": "external",
                "timestamp": "2026-01-01T12:00:00Z",
                "price": 100.0,
                "confidence": "high",
            }
        ],
        "notes": "clear body-close break",
    }
    if adjudicated_by is None:
        payload.pop("adjudicated_by")
    return {"perception_annotations": payload}


def _write_case_lab_case(root: Path) -> Path:
    case_dir = root / "BTCUSDT" / "BTCUSDT_unit_perception_candidate"
    charts_dir = case_dir / "raw_charts"
    charts_dir.mkdir(parents=True)
    chart_path = charts_dir / "raw_15.png"
    chart_path.write_bytes(b"png")
    case = {
        "case_id": "BTCUSDT_unit_perception_candidate",
        "symbol": "BTCUSDT",
        "decision_time": "2026-01-01T12:00:00",
        "chart_evidence": {"screenshots": {"15": str(chart_path.resolve())}},
        "data": {"analysis_window_csv": str((case_dir / "analysis_window_15m.csv").resolve())},
    }
    (case_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
    (case_dir / "reviewer_a.json").write_text(json.dumps(_annotation_payload(status="reviewed", reviewer_ids=["reviewer_a"])), encoding="utf-8")
    (case_dir / "reviewer_b.json").write_text(json.dumps(_annotation_payload(status="reviewed", reviewer_ids=["reviewer_b"])), encoding="utf-8")
    adjudicated = _annotation_payload(status="adjudicated", reviewer_ids=["reviewer_a", "reviewer_b"], adjudicated_by="lead")
    adjudicated["adjudicator_justification"] = "Both reviewers identified the same external BOS."
    (case_dir / "adjudicated.json").write_text(json.dumps(adjudicated), encoding="utf-8")
    (case_dir / "engine_weak_labels.json").write_text(
        json.dumps({"truth_status": "weak_operational_labels_only", "objects": []}),
        encoding="utf-8",
    )
    return case_dir


def test_measure_review_agreement_builds_human_baseline(tmp_path: Path) -> None:
    _write_case_lab_case(tmp_path)

    report = build_agreement_report(root=tmp_path, reviewers=["reviewer_a", "reviewer_b"], min_cases=1)

    assert report["status"] == "ready_for_ai_promotion_baseline"
    assert report["overall"]["f1"] == 1.0
    assert report["per_primitive"]["bos"]["tp"] == 1


def test_export_adjudication_dataset_requires_adjudicated_labels(tmp_path: Path) -> None:
    _write_case_lab_case(tmp_path)

    rows, skipped = build_rows(tmp_path, ["reviewer_a", "reviewer_b"])

    assert not skipped
    assert len(rows) == 1
    assert rows[0]["adjudication"]["justification"] == "Both reviewers identified the same external BOS."
    assert rows[0]["engine_weak_labels"]["truth_status"] == "weak_operational_labels_only"


def test_desktop_ai_review_packet_stays_blind_to_machine_outputs(tmp_path: Path) -> None:
    _write_case_lab_case(tmp_path)
    out = tmp_path / "packets"

    manifest = build_packets(tmp_path, out, "desktop_ai", limit=1)
    prompt = Path(manifest["packets"][0]["prompt"]).read_text(encoding="utf-8")
    response = json.loads(Path(manifest["packets"][0]["response_template"]).read_text(encoding="utf-8"))

    assert manifest["mode"] == "desktop_ai_no_api"
    assert "engine_weak_labels" not in prompt
    assert "machine_analysis" not in prompt
    assert response["source"] == "desktop_ai_no_api"
    assert response["perception_annotations"]["label_status"] == "draft"
