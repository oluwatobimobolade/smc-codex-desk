from __future__ import annotations

from pathlib import Path

import pandas as pd

from smc_desk.brain.llm_provider import LLMCompletionRequest
from tools import run_wp0036_acceptance_gauntlet as gauntlet


def _evidence_pack() -> dict:
    summaries = {
        "15m": {"first_open": 100.0, "last_close": 95.0, "high": 105.0, "low": 90.0},
        "1h": {"first_open": 100.0, "last_close": 95.0, "high": 105.0, "low": 90.0},
        "4h": {"first_open": 100.0, "last_close": 95.0, "high": 105.0, "low": 90.0},
        "1d": {"first_open": 100.0, "last_close": 95.0, "high": 105.0, "low": 90.0},
    }
    return {
        "schema": "smc_evidence_pack_v1",
        "symbol": "BTCUSDT",
        "ohlcv_summaries": summaries,
        "active_range_authority": {
            "selected_range": {
                "status": "RESOLVED_ACTIVE_RANGE",
                "timeframe": "4h",
                "direction": "bearish",
                "range_high": 105.0,
                "range_low": 90.0,
                "equilibrium": 97.5,
                "price_location": "discount",
                "range_id": "test-range",
                "protected_high": 105.0,
                "protected_low": 90.0,
                "width_atr": 4.0,
                "max_width_atr": 22.0,
                "authority_notes": ["test structural range"],
            }
        },
    }


def _request(prompt: str = '{"role":"AI SMC trader brain"}') -> LLMCompletionRequest:
    return LLMCompletionRequest(prompt=prompt, evidence_pack=_evidence_pack(), chart_images={})


def _df(rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01", periods=rows, freq="15min", tz="UTC"),
            "open": [100.0 + index * 0.1 for index in range(rows)],
            "high": [101.0 + index * 0.1 for index in range(rows)],
            "low": [99.0 + index * 0.1 for index in range(rows)],
            "close": [100.3 + index * 0.1 for index in range(rows)],
            "volume": [1000.0 for _ in range(rows)],
        }
    )


def test_wp0036_payload_does_not_force_trade_plan_without_validated_sequence():
    payload = gauntlet.build_gauntlet_ai_payload(_request(), "BTCUSDT", {})

    assert payload["official_state"] != "TRADE_PLAN_READY"
    assert payload["entry_plan"]["entry_price"] is None
    assert payload["stop_loss_plan"]["stop_price"] is None
    assert payload["target_plan"]["targets"] == []
    assert payload["annotation_plan"]["show_trade_box"] is False


def test_wp0036_payload_returns_critic_json_for_critic_prompt():
    payload = gauntlet.build_gauntlet_ai_payload(
        _request('{"role":"AI SMC Critic Colleague"}'),
        "BTCUSDT",
        {},
    )

    assert set(payload) == {"veto", "critique", "suggested_downgrade_state"}
    assert payload["veto"] is False


def test_wp0036_clean_chart_renderer_uses_full_depth(monkeypatch, tmp_path):
    captured = {}

    def fake_render(df, output_path: Path, *, symbol: str, timeframe: str) -> None:
        captured["rows"] = len(df)
        captured["symbol"] = symbol
        captured["timeframe"] = timeframe
        Path(output_path).write_bytes(b"png")

    monkeypatch.setattr(gauntlet, "render_clean_candle_chart", fake_render)

    gauntlet.plot_clean_chart(_df(1500), "15m", tmp_path / "clean.png", "BTCUSDT")

    assert captured == {"rows": 1500, "symbol": "BTCUSDT", "timeframe": "15m"}


def test_wp0036_acceptance_summary_fails_state_trade_box_mismatch():
    summary = gauntlet.perform_acceptance_checkpoints(
        symbol="BTCUSDT",
        result=type("Result", (), {"status": "PASS", "report": {}})(),
        evidence_pack={},
        official_decision={
            "official_state": "WATCH_ONLY",
            "annotation_plan": {"chart_template": "trade_plan_chart", "show_trade_box": True, "labels": []},
        },
        validation_result_data={},
        provider_manifest={"provider_mode": "REAL_VISION_LLM_PROVIDER", "is_real_llm_call": True, "is_manual": False, "is_stub": False},
        critic_data={"veto": False, "critique": "", "suggested_downgrade_state": "KEEP_CURRENT"},
        anchor_grounding={"anchors": []},
        liq_status={"swept_liquidity_checks": []},
        timeframe_dfs={"15m": _df(10), "1h": _df(10), "4h": _df(10), "1d": _df(10)},
    )

    assert "checkpoint_7_watch_layout_trade_box" in summary
    assert "checkpoint_8_trade_chart_state_mismatch" in summary
    assert "checkpoint_11_context_depth_shallow" in summary
    assert "FINAL ACCEPTANCE STATUS FOR BTCUSDT: FAIL" in summary


def test_watch_invalidation_is_not_reported_as_failed_executable_anchor():
    report = gauntlet.build_anchor_grounding_report(
        {
            "official_state": "WATCH_ONLY",
            "entry_plan": {"entry_ready": False},
            "stop_loss_plan": {},
            "invalidation": {
                "invalidation_price": 105.0,
                "mapped_invalidation_price": None,
                "invalidation_anchor": None,
                "evidence_object_ids": [],
            },
            "target_plan": {"targets": []},
        },
        {"detector_candidates": {}},
    )

    assert report["anchors"][0]["field"] == "invalidation"
    assert report["anchors"][0]["status"] == "not_applicable_watch_reference"
