from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from smc_desk.colleague.outcome_resolution import resolve_outcome_contract, resolve_run_outcome


def _contract(direction: str = "bullish", action: str = "PAPER_EXECUTE_DISABLED") -> dict:
    target = 105.0 if direction == "bullish" else 95.0
    invalidation = 97.0 if direction == "bullish" else 105.0
    return {
        "outcome_contract_version": "0.1",
        "status": "pending_observation",
        "symbol": "BTCUSDT",
        "decision_available_at": "2025-01-01T00:15:00",
        "resolution_due_at": "2025-01-01T01:15:00",
        "horizon_bars_15m": 4,
        "decision_action": action,
        "capital_risk": 0,
        "tracked_scenarios": [
            {
                "scenario_id": "scenario:test",
                "direction": direction,
                "setup_stage": "execution_candidate_policy_disabled",
                "terminal_conditions": {
                    "target_touch": [target],
                    "invalidation": [{"type": "execution_invalidation", "price": invalidation}],
                },
            }
        ],
    }


def _future(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [row[0] for row in rows],
            "open": [100.0] * len(rows),
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [100.0] * len(rows),
            "volume": [1_000.0] * len(rows),
        }
    )


def test_resolves_bullish_target_before_invalidation() -> None:
    result = resolve_outcome_contract(
        contract=_contract("bullish"),
        ohlcv=_future(
            [
                ("2025-01-01T00:15:00", 103.0, 99.0),
                ("2025-01-01T00:30:00", 105.5, 99.0),
                ("2025-01-01T00:45:00", 104.0, 96.0),
                ("2025-01-01T01:00:00", 101.0, 98.0),
            ]
        ),
    )

    assert result["status"] == "resolved_hypothetical_disabled_signal"
    assert result["scenario_results"][0]["status"] == "target_touched_first"
    assert result["scenario_results"][0]["hypothetically_favorable"] is True
    assert result["market_edge_claimed"] is False


def test_resolves_bearish_invalidation_before_target() -> None:
    result = resolve_outcome_contract(
        contract=_contract("bearish"),
        ohlcv=_future(
            [
                ("2025-01-01T00:15:00", 106.0, 99.0),
                ("2025-01-01T00:30:00", 104.0, 94.0),
                ("2025-01-01T00:45:00", 103.0, 93.0),
                ("2025-01-01T01:00:00", 101.0, 98.0),
            ]
        ),
    )

    assert result["scenario_results"][0]["status"] == "invalidated_first"
    assert result["scenario_results"][0]["hypothetically_favorable"] is False


def test_flags_same_candle_target_and_invalidation_as_ambiguous() -> None:
    result = resolve_outcome_contract(
        contract=_contract("bullish"),
        ohlcv=_future(
            [
                ("2025-01-01T00:15:00", 106.0, 96.0),
                ("2025-01-01T00:30:00", 104.0, 99.0),
                ("2025-01-01T00:45:00", 103.0, 98.0),
                ("2025-01-01T01:00:00", 101.0, 98.0),
            ]
        ),
    )

    assert result["scenario_results"][0]["status"] == "ambiguous_same_candle"
    assert result["scenario_results"][0]["hypothetically_favorable"] is None


def test_waits_when_future_window_is_incomplete() -> None:
    result = resolve_outcome_contract(
        contract=_contract("bullish"),
        ohlcv=_future([("2025-01-01T00:15:00", 103.0, 99.0)]),
    )

    assert result["status"] == "unresolved_waiting_for_future_candles"
    assert result["future_window"]["available_bars"] == 1
    assert result["scenario_results"] == []


def test_no_setup_outcome_is_observation_not_hypothetical_performance() -> None:
    result = resolve_outcome_contract(
        contract=_contract("bullish", action="NO_SETUP"),
        ohlcv=_future(
            [
                ("2025-01-01T00:15:00", 103.0, 99.0),
                ("2025-01-01T00:30:00", 105.5, 99.0),
                ("2025-01-01T00:45:00", 104.0, 98.0),
                ("2025-01-01T01:00:00", 101.0, 98.0),
            ]
        ),
    )

    assert result["status"] == "resolved_no_setup_observation"
    assert result["scenario_results"][0]["status"] == "observed_target_touched_first_no_trade"
    assert result["scenario_results"][0]["hypothetically_favorable"] is None


def test_resolve_run_outcome_writes_resolution_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "outcome").mkdir(parents=True)
    (run_dir / "outcome" / "pending.json").write_text(json.dumps(_contract("bullish")), encoding="utf-8")
    source = tmp_path / "source.csv"
    _future(
        [
            ("2025-01-01T00:00:00", 100.0, 99.0),
            ("2025-01-01T00:15:00", 103.0, 99.0),
            ("2025-01-01T00:30:00", 105.5, 99.0),
            ("2025-01-01T00:45:00", 104.0, 98.0),
            ("2025-01-01T01:00:00", 101.0, 98.0),
        ]
    ).to_csv(source, index=False)
    (run_dir / "source_manifest.json").write_text(json.dumps({"source_path": str(source)}), encoding="utf-8")

    result = resolve_run_outcome(run_dir=run_dir)

    assert (run_dir / "outcome" / "resolution.json").exists()
    assert result["scenario_results"][0]["status"] == "target_touched_first"
