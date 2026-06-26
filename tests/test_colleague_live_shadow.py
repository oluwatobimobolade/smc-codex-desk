from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smc_desk.colleague.live_shadow import run_live_shadow_universe
from smc_desk.colleague.request_contract import ColleagueRunRequest
from smc_desk.rules import RuleConfig


def test_live_shadow_universe_isolates_symbol_runs(tmp_path: Path) -> None:
    def fake_market(**kwargs: Any) -> tuple[Path, dict[str, Any]]:
        symbol = kwargs["symbol"]
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True)
        source = output_dir / f"{symbol}_15m_verified_closed.csv"
        source.write_text(
            "timestamp,open,high,low,close,volume,close_time,trade_count,source,is_final,is_complete\n"
            "2025-01-01T00:00:00,1,2,0.5,1,10,2025-01-01T00:14:59.999000+00:00,2,test,true,true\n",
            encoding="utf-8",
        )
        manifest = {
            "status": "VERIFIED",
            "fetched_at": "2025-01-01T00:15:01+00:00",
            "source_csv": str(source),
            "last_closed_candle_open": "2025-01-01T00:00:00+00:00",
            "last_closed_candle_close": "2025-01-01T00:14:59.999000+00:00",
        }
        path = output_dir / "verified_closed_ohlcv_manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def fake_capture(**kwargs: Any) -> tuple[Path, dict[str, Any]]:
        symbol = kwargs["symbol"]
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True)
        source = output_dir / "ohlcv" / f"{symbol}_15m_tradingview.csv"
        source.parent.mkdir(parents=True)
        source.write_text("timestamp,open,high,low,close,volume,source\n2025-01-01T00:00:00,1,2,0,1,10,test\n", encoding="utf-8")
        manifest = {
            "instrument": symbol,
            "tradingview_symbol": f"BINANCE:{symbol}.P",
            "chart_state": {
                "timeframes": {
                    "15m": {
                        "last_closed_candle_open": "2025-01-01T00:00:00",
                        "last_closed_candle_close": "2025-01-01T00:15:00",
                    }
                }
            },
        }
        path = output_dir / "tradingview_alignment_manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def fake_analysis(request: ColleagueRunRequest, _config: RuleConfig) -> dict[str, Any]:
        run_dir = Path(str(request.output_dir))
        (run_dir / "scenarios").mkdir(parents=True)
        (run_dir / "external").mkdir(parents=True)
        (run_dir / "perception").mkdir(parents=True)
        (run_dir / "outcome").mkdir(parents=True)
        (run_dir / "reports").mkdir(parents=True)
        (run_dir / "request.json").write_text("{}", encoding="utf-8")
        (run_dir / "scenarios" / "decision.json").write_text(json.dumps({"action": "NO_SETUP", "capital_risk": 0}), encoding="utf-8")
        (run_dir / "external" / "alignment_report.json").write_text(json.dumps({"status": "PASS", "blocking_failures": []}), encoding="utf-8")
        (run_dir / "perception" / "mtf_state_graph.json").write_text(
            json.dumps(
                {
                    "graph_version": "0.3",
                    "nodes": [{"node_id": "a"}],
                    "edges": [{"from": "a", "to": "b"}],
                    "semantic_overlay": {"summary": {"liquidity_pool_candidate": 1}},
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "outcome" / "pending.json").write_text(json.dumps({"status": "pending_observation", "resolution_due_at": "2025-01-02T00:00:00"}), encoding="utf-8")
        (run_dir / "reports" / "colleague_thesis.md").write_text("# Thesis\n", encoding="utf-8")
        manifest = {
            "run_id": f"{request.normalized_symbol}_live_shadow",
            "decision_candle_open": "2025-01-01T00:00:00",
            "decision_available_at": "2025-01-01T00:15:00",
            "files": {"request.json": {"path": str(run_dir / "request.json")}},
        }
        (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    summary = run_live_shadow_universe(
        symbols=["btcusd", "ethusdt"],
        output_root=tmp_path / "universe",
        config=RuleConfig(),
        market_data_fn=fake_market,
        capture_fn=fake_capture,
        analysis_fn=fake_analysis,
    )

    assert summary["status"] == "PASS"
    assert summary["symbols_completed"] == ["BTCUSDT", "ETHUSDT"]
    assert (tmp_path / "universe" / "summary.json").exists()
    assert all(item["alignment_status"] == "PASS" for item in summary["symbols"])
