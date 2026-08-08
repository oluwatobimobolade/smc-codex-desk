from __future__ import annotations

import pandas as pd

from smc_desk.perception.sweep_lifecycle import classify_sweep_lifecycle, enrich_sweep_lifecycles


def _candles(closes: list[float]) -> list[dict]:
    rows = []
    for index, close in enumerate(closes):
        timestamp = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=15 * index)
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": close + 0.2,
                "high": 101.0 if index == 0 else max(close + 0.3, 100.1),
                "low": min(close - 0.3, 99.0),
                "close": close,
            }
        )
    return rows


def _sweep() -> dict:
    return {
        "object_id": "sweep-1",
        "direction": "bearish",
        "candidate_at": "2026-01-01T00:00:00Z",
        "confirmed_at": "2026-01-01T00:15:00Z",
        "evidence": {"swept_price": 100.0, "reclaim_confirmed": True},
    }


def test_reclaim_is_only_candidate_before_structural_consequence() -> None:
    result = classify_sweep_lifecycle(
        sweep=_sweep(),
        candles=_candles([99.5, 99.2]),
        structure_breaks=[],
        decision_time="2026-01-01T00:15:00Z",
    )
    assert result["state"] == "RECLAIM_CANDIDATE"
    assert result["structural_sweep_confirmed"] is False


def test_two_closes_beyond_pool_become_accepted_breakout_not_sweep() -> None:
    result = classify_sweep_lifecycle(
        sweep=_sweep(),
        candles=_candles([99.5, 100.4, 100.8]),
        structure_breaks=[],
        decision_time="2026-01-01T00:30:00Z",
    )
    assert result["state"] == "ACCEPTED_BREAKOUT"
    assert result["structural_sweep_confirmed"] is False


def test_reclaim_plus_opposing_structure_confirms_structural_sweep() -> None:
    result = classify_sweep_lifecycle(
        sweep=_sweep(),
        candles=_candles([99.5, 99.0, 98.5, 98.0]),
        structure_breaks=[
            {
                "object_id": "break-down",
                "direction": "bearish",
                "confirmation_status": "confirmed",
                "confirmed_at": "2026-01-01T00:30:00Z",
                "evidence": {"is_unconfirmed_probe": False},
            }
        ],
        decision_time="2026-01-01T00:45:00Z",
    )
    assert result["state"] == "CONFIRMED_STRUCTURAL_SWEEP"
    assert result["structural_sweep_confirmed"] is True
    assert result["structural_consequence_id"] == "break-down"


def test_enrichment_downgrades_same_candle_sweep_until_consequence() -> None:
    rows = _candles([99.5, 99.2])
    enriched = enrich_sweep_lifecycles(
        {"15m": {"sweeps": [_sweep()], "structure_breaks": []}},
        {"15m": pd.DataFrame(rows)},
        decision_time="2026-01-01T00:15:00Z",
    )
    sweep = enriched["15m"]["sweeps"][0]
    assert sweep["confirmation_status"] == "provisional"
    assert sweep["truth_status"] == "reclaim_candidate"
