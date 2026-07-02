from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smc_desk.rules import RuleConfig
from tools.build_resolved_case_cohort import build_resolved_case_cohort, select_decision_times


def _write_ohlcv(path: Path, periods: int = 640) -> None:
    timestamps = pd.date_range("2025-01-01", periods=periods, freq="15min")
    close = [100.0 + index * 0.01 for index in range(periods)]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": [value + 0.05 for value in close],
            "volume": [1000.0 + index for index in range(periods)],
        }
    ).to_csv(path, index=False)


def test_select_decision_times_are_evenly_spaced_and_resolvable() -> None:
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=620, freq="15min")})

    selected = select_decision_times(df, count=3, horizon_bars=8, min_history_bars=20)

    assert len(selected) == 3
    assert selected == sorted(selected)
    assert all(item.minute in {0, 15, 30, 45} for item in selected)


def test_build_resolved_case_cohort_writes_honest_summary(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_ohlcv(data_root / "BTCUSDT" / "BTCUSDT_15m_unit.csv")

    summary = build_resolved_case_cohort(
        symbols=["BTCUSDT"],
        output_root=tmp_path / "cohort",
        config=RuleConfig(),
        cases_per_symbol=2,
        horizon_bars=4,
        data_root=data_root,
        tag="unit",
        include_legacy_comparison=False,
        render_charts=False,
        holdout_policy=str(tmp_path / "missing_holdout.json"),
    )

    assert summary["total_packages"] == 2
    assert summary["resolved_packages"] == 2
    assert summary["cohort_bucket_counts"]["no_trade_observation"] == 2
    assert summary["cohort_bucket_counts"]["unresolved"] == 0
    assert summary["market_edge_claimed"] is False
    assert summary["promotion_status"] == "not_eligible_edge_not_tested"
    assert Path(summary["case_records_path"]).exists()
    run_manifest_path = Path(summary["cases"][0]["run_manifest"])
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    assert run_manifest["legacy_engine_role"] == "disabled"
    assert "charts/render_status.json" in run_manifest["files"]
