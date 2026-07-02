from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smc_desk.rules import RuleConfig
from smc_desk.colleague.tradingview_live_manifest import build_manifest_from_closed_data
from smc_desk.colleague.smc_semantics import build_semantic_overlay
from tools.run_market_colleague_case import build_market_colleague_case, default_ohlcv_path, normalize_symbol


def _candles(count: int = 720) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=count, freq="15min")
    close = [100.0 + index * 0.02 for index in range(count)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 0.45 for value in close],
            "low": [value - 0.45 for value in close],
            "close": [value + 0.1 for value in close],
            "volume": [1_000.0 + index for index in range(count)],
        }
    )


def _stub_renderers(monkeypatch) -> None:
    def raw_stub(_df, *, symbol: str, timeframe: str, output_path: str) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(f"{symbol}-{timeframe}".encode())

    def annotated_stub(_df, _analysis, output_path: str, **_kwargs) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"annotated")

    monkeypatch.setattr("smc_desk.colleague.orchestrator.render_raw_chart", raw_stub)
    monkeypatch.setattr("smc_desk.colleague.orchestrator.render_smc_annotated", annotated_stub)
    monkeypatch.setattr(
        "smc_desk.colleague.orchestrator.render_mtf_mosaic",
        lambda _dfs, _snapshots, output_path, title="": Path(output_path).write_bytes(b"mosaic"),
    )


def _chart_state(decision_open: str = "2025-01-07T11:45:00", symbol: str = "BINANCE:SOLUSDT.P") -> dict:
    close_time = (pd.Timestamp(decision_open) + pd.Timedelta(minutes=15)).isoformat()
    return {
        "symbol": symbol,
        "exchange": "BINANCE",
        "instrument": "SOLUSDT",
        "candle_type": "candles",
        "scale": "linear",
        "timezone": "UTC",
        "timeframes": {
            "15m": {
                "interval": "15",
                "last_closed_candle_open": decision_open,
                "last_closed_candle_close": close_time,
            },
            "1h": {
                "interval": "60",
                "last_closed_candle_open": "2025-01-07T11:00:00",
                "last_closed_candle_close": "2025-01-07T12:00:00",
            },
            "4h": {
                "interval": "240",
                "last_closed_candle_open": "2025-01-07T08:00:00",
                "last_closed_candle_close": "2025-01-07T12:00:00",
            },
            "1d": {
                "interval": "1D",
                "last_closed_candle_open": "2025-01-06T00:00:00",
                "last_closed_candle_close": "2025-01-07T00:00:00",
            },
        },
    }


def test_market_colleague_case_builds_complete_local_artifacts(tmp_path: Path, monkeypatch) -> None:
    _stub_renderers(monkeypatch)

    source = tmp_path / "BTCUSDT_15m_unit.csv"
    _candles().to_csv(source, index=False)

    manifest = build_market_colleague_case(
        symbol="btcusd",
        source_path=source,
        output_dir=tmp_path / "case",
        config=RuleConfig(),
        decision_time="2025-01-07T12:00:00Z",
        holdout_policy=tmp_path / "missing_holdout.json",
    )

    case_dir = Path(manifest["files"]["request.json"]["path"]).parent
    assert manifest["symbol"] == "BTCUSDT"
    assert manifest["package_kind"] == "market_colleague_analysis_run"
    assert manifest["primary_perception_source"] == "PerceptionEngineV2"
    assert manifest["legacy_engine_role"] == "comparison_only"
    assert manifest["no_future_leakage"]["history_ends_at_decision_candle_open"] is True

    required = [
        "perception/objects.json",
        "perception/mtf_state_graph.json",
        "perception/confirmed_state.json",
        "perception/provisional_state.json",
        "scenarios/scenario_tree.json",
        "scenarios/decision.json",
        "legacy_comparison/engine_analysis.json",
        "authority_manifest.json",
        "reports/colleague_thesis.md",
        "reports/independent_review_prompt.md",
        "charts/mtf_mosaic.png",
    ]
    for name in required:
        file_info = manifest["files"][name]
        assert Path(file_info["path"]).exists()
        assert file_info["sha256"]

    assert {f"charts/clean/BTCUSDT_{tf}_clean.png" for tf in ("15m", "1h", "4h", "1d")}.issubset(manifest["files"])
    assert "PerceptionEngineV2 is the primary" in (case_dir / "reports" / "colleague_thesis.md").read_text(encoding="utf-8")
    assert "Do not inspect `legacy_comparison/`" in (case_dir / "reports" / "independent_review_prompt.md").read_text(encoding="utf-8")

    engine = json.loads((case_dir / "legacy_comparison" / "engine_analysis.json").read_text(encoding="utf-8"))
    perception = json.loads((case_dir / "perception" / "objects.json").read_text(encoding="utf-8"))
    authority = json.loads((case_dir / "authority_manifest.json").read_text(encoding="utf-8"))
    alignment = json.loads((case_dir / "external" / "alignment_report.json").read_text(encoding="utf-8"))
    mtf_graph = json.loads((case_dir / "perception" / "mtf_state_graph.json").read_text(encoding="utf-8"))
    scenario_tree = json.loads((case_dir / "scenarios" / "scenario_tree.json").read_text(encoding="utf-8"))
    evidence_graph = json.loads((case_dir / "scenarios" / "evidence_graph.json").read_text(encoding="utf-8"))
    assert engine["symbol"] == "BTCUSDT"
    assert perception["source"] == "PerceptionEngineV2"
    assert set(perception["timeframes"]) == {"15m", "1h", "4h", "1d"}
    assert authority["legacy_engine"] == "comparison_only"
    assert authority["live_execution"] == "disabled"
    assert alignment["status"] == "NOT_ATTACHED"
    assert mtf_graph["graph_version"] == "0.3"
    assert "market_story" in mtf_graph
    assert "semantic_overlay" in mtf_graph
    assert any(node["object_type"] == "decision_state" for node in mtf_graph["nodes"])
    assert mtf_graph["semantic_overlay"]["authority"] == "candidate_semantics_not_gold_truth"
    assert scenario_tree["scenario_tree_version"] == "0.3"
    assert scenario_tree["scenarios"][0]["setup_stage"]
    assert evidence_graph["status"] == "built"
    assert evidence_graph["node_count"] == len(mtf_graph["nodes"])
    decision = json.loads((case_dir / "scenarios" / "decision.json").read_text(encoding="utf-8"))
    assert decision["legacy_trade_plan_used"] is False
    assert decision["authority_source"] == "PerceptionEngineV2+MTF_CONTEXT"
    event_lines = (case_dir / "perception" / "event_ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any(json.loads(line)["event_type"] == "decision.final" for line in event_lines)
    pending = json.loads((case_dir / "outcome" / "pending.json").read_text(encoding="utf-8"))
    similar = json.loads((case_dir / "prediction" / "similar_cases.json").read_text(encoding="utf-8"))
    assert pending["outcome_contract_version"] == "0.1"
    assert pending["status"] == "pending_observation"
    assert similar["method"] == "deterministic_signature_overlap_v0"


def test_market_colleague_runs_with_legacy_comparison_disabled(tmp_path: Path, monkeypatch) -> None:
    _stub_renderers(monkeypatch)

    def fail_if_legacy_runs(*_args, **_kwargs):
        raise AssertionError("legacy analyze_dataframe should not run when include_legacy_comparison=false")

    # Patch the underlying import, not the orchestrator (which no longer top-level imports it)
    monkeypatch.setattr("smc_desk.engine.analyze_dataframe", fail_if_legacy_runs)
    source = tmp_path / "BTCUSDT_15m_unit.csv"
    _candles().to_csv(source, index=False)

    manifest = build_market_colleague_case(
        symbol="BTCUSDT",
        source_path=source,
        output_dir=tmp_path / "case_no_legacy",
        config=RuleConfig(),
        decision_time="2025-01-07T12:00:00Z",
        holdout_policy=tmp_path / "missing_holdout.json",
        include_legacy_comparison=False,
    )

    case_dir = Path(manifest["files"]["request.json"]["path"]).parent
    assert manifest["legacy_engine_role"] == "disabled"
    assert "legacy_comparison/engine_analysis.json" not in manifest["files"]
    assert "legacy_comparison/trade_plan.md" not in manifest["files"]
    assert "charts/perception/BTCUSDT_15m_legacy_comparison_annotated.png" not in manifest["files"]
    assert "legacy_comparison/status.json" in manifest["files"]
    assert "charts/perception/legacy_annotation_status.json" in manifest["files"]

    authority = json.loads((case_dir / "authority_manifest.json").read_text(encoding="utf-8"))
    status = json.loads((case_dir / "legacy_comparison" / "status.json").read_text(encoding="utf-8"))
    decision = json.loads((case_dir / "scenarios" / "decision.json").read_text(encoding="utf-8"))
    scenario_tree = json.loads((case_dir / "scenarios" / "scenario_tree.json").read_text(encoding="utf-8"))
    thesis = (case_dir / "reports" / "colleague_thesis.md").read_text(encoding="utf-8")

    assert authority["legacy_engine"] == "disabled"
    assert status["status"] == "disabled"
    assert decision["legacy_trade_plan_used"] is False
    assert decision["authority_source"] == "PerceptionEngineV2+MTF_CONTEXT"
    assert decision["reason"].startswith("Current decision is derived from PerceptionEngineV2")
    assert scenario_tree["scenarios"][0]["target_definition"]["status"] == "not_defined_no_execution_plan"
    assert "Legacy comparison verdict: `disabled`" in thesis
    assert "Legacy comparison disabled for this run." in thesis


def test_market_colleague_default_path_and_symbol_normalization() -> None:
    assert normalize_symbol("btc-usd") == "BTCUSDT"
    assert default_ohlcv_path("ETHUSD").as_posix().endswith("ETHUSDT/ETHUSDT_15m_4year.csv")


def test_market_colleague_attaches_and_verifies_tradingview_manifest(tmp_path: Path, monkeypatch) -> None:
    _stub_renderers(monkeypatch)

    source = tmp_path / "SOLUSDT_15m_unit.csv"
    _candles().to_csv(source, index=False)
    screenshots = {}
    for label in ("15", "1H", "4H", "1D"):
        tv_image = tmp_path / f"tv_{label}.png"
        tv_image.write_bytes(f"tradingview-{label}".encode())
        screenshots[label] = str(tv_image)
    tv_manifest = tmp_path / "screenshots.json"
    tv_manifest.write_text(
        json.dumps(
            {
                "instrument": "SOLUSDT",
                "exchange": "BINANCE",
                "tradingview_symbol": "BINANCE:SOLUSDT.P",
                "screenshots": screenshots,
                "chart_state": _chart_state(),
            }
        ),
        encoding="utf-8",
    )

    manifest = build_market_colleague_case(
        symbol="SOLUSDT",
        source_path=source,
        output_dir=tmp_path / "case",
        config=RuleConfig(),
        decision_time="2025-01-07T12:00:00Z",
        tradingview_manifest=tv_manifest,
        holdout_policy=tmp_path / "missing_holdout.json",
    )

    case_dir = Path(manifest["files"]["request.json"]["path"]).parent
    capture = json.loads((case_dir / "external" / "capture_manifest.json").read_text(encoding="utf-8"))
    alignment = json.loads((case_dir / "external" / "alignment_report.json").read_text(encoding="utf-8"))
    assert capture["status"] == "attached"
    assert capture["manifest_sha256"]
    assert capture["screenshot_hashes"]["15"]["exists"] is True
    assert capture["screenshot_hashes"]["15"]["sha256"]
    assert alignment["status"] == "PASS"
    assert alignment["passed"] is True


def test_market_colleague_wrong_tradingview_symbol_blocks_decision(tmp_path: Path, monkeypatch) -> None:
    _stub_renderers(monkeypatch)

    source = tmp_path / "SOLUSDT_15m_unit.csv"
    _candles().to_csv(source, index=False)
    screenshots = {}
    for label in ("15", "1H", "4H", "1D"):
        tv_image = tmp_path / f"wrong_{label}.png"
        tv_image.write_bytes(f"wrong-{label}".encode())
        screenshots[label] = str(tv_image)
    tv_manifest = tmp_path / "wrong_screenshots.json"
    tv_manifest.write_text(
        json.dumps(
            {
                "instrument": "SOLUSDT",
                "exchange": "BINANCE",
                "tradingview_symbol": "BINANCE:BTCUSDT.P",
                "screenshots": screenshots,
                "chart_state": _chart_state(symbol="BINANCE:BTCUSDT.P"),
            }
        ),
        encoding="utf-8",
    )

    manifest = build_market_colleague_case(
        symbol="SOLUSDT",
        source_path=source,
        output_dir=tmp_path / "case",
        config=RuleConfig(),
        decision_time="2025-01-07T12:00:00Z",
        tradingview_manifest=tv_manifest,
        holdout_policy=tmp_path / "missing_holdout.json",
    )

    case_dir = Path(manifest["files"]["request.json"]["path"]).parent
    alignment = json.loads((case_dir / "external" / "alignment_report.json").read_text(encoding="utf-8"))
    decision = json.loads((case_dir / "scenarios" / "decision.json").read_text(encoding="utf-8"))
    assert alignment["status"] == "FAIL"
    assert any(check["name"] == "tradingview_symbol" for check in alignment["blocking_failures"])
    assert decision["action"] == "SOURCE_MISMATCH"


def test_tradingview_live_manifest_payload_builds_chart_state(tmp_path: Path) -> None:
    screenshots = {}
    ohlcv = {}
    closed = {}
    for tf, label, open_time in [
        ("15m", "15", "2025-01-07T12:00:00+00:00"),
        ("1h", "1H", "2025-01-07T11:00:00+00:00"),
        ("4h", "4H", "2025-01-07T08:00:00+00:00"),
        ("1d", "1D", "2025-01-06T00:00:00+00:00"),
    ]:
        image = tmp_path / f"{label}.png"
        image.write_bytes(label.encode())
        screenshots[tf] = image
        csv_path = tmp_path / f"{tf}.csv"
        csv_path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
        ohlcv[tf] = csv_path
        closed[tf] = [{"timestamp": open_time, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    manifest = build_manifest_from_closed_data(
        symbol="SOLUSDT",
        tradingview_symbol="BINANCE:SOLUSDT.P",
        output_dir=tmp_path,
        screenshots=screenshots,
        ohlcv_paths=ohlcv,
        closed_by_tf=closed,
    )

    assert manifest["tradingview_symbol"] == "BINANCE:SOLUSDT.P"
    assert manifest["screenshots"]["15"].endswith("15.png")
    assert manifest["chart_state"]["timeframes"]["15m"]["last_closed_candle_close"] == "2025-01-07T12:15:00+00:00"


def test_semantic_overlay_builds_liquidity_and_inducement_candidates() -> None:
    perception = {
        "15m": {
            "swings": {
                "external": [
                    {
                        "object_id": "swing-high",
                        "direction": "bearish",
                        "price_high": "105.0",
                        "price_low": "104.0",
                        "confirmed_at": "2025-01-01T01:00:00Z",
                        "confidence": 0.8,
                    },
                    {
                        "object_id": "swing-low",
                        "direction": "bullish",
                        "price_high": "96.0",
                        "price_low": "95.0",
                        "confirmed_at": "2025-01-01T02:00:00Z",
                        "confidence": 0.8,
                    },
                ]
            },
            "structure_breaks": [],
            "fvgs": [],
        }
    }
    overlay = build_semantic_overlay(
        perception_by_tf=perception,
        mtf_snapshot={"execution_consensus": "bearish"},
        legacy_analysis={"trade_plan": {}},
    )

    types = {node["object_type"] for node in overlay["nodes"]}
    assert "liquidity_pool_candidate" in types
    assert "inducement_candidate" in types
    assert overlay["summary"]["liquidity_pool_candidate"] == 2
