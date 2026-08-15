import pytest
import pandas as pd
from datetime import datetime, timezone
from smc_desk.rules import RuleConfig, load_rule_config
from smc_desk.brain.ai_smc_trader_brain import AISMCDecision
from smc_desk.brain.ai_smc_consistency_validator import validate_ai_smc_decision, ValidationResult
from smc_desk.mtf import resample_to_ny_close_daily
from smc_desk.data.timeframe_reconstruction import (
    resample_to_ny_close_daily as resample_to_ny_close_daily_canonical,
)


def test_validation_decoupling_bad_rr():
    # Setup a dummy decision with a bad RR (e.g. 1.5) but otherwise valid SMC structure
    raw_decision = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY",
        "setup_grade": "A",
        "direction": "bullish",
        "setup_model": "bullish_continuation",
        "bias_summary": {
            "daily": "bullish",
            "4h": "bullish",
            "1h": "bullish",
            "final_bias": "bullish",
            "evidence": []
        },
        "active_range": {
            "timeframe": "15m",
            "high": 4095.0,
            "low": 4050.0,
            "equilibrium": 4072.5,
            "price_location": "discount",
            "source": "active_range_authority"
        },
        "liquidity_story": {
            "obvious_liquidity": [],
            "swept_liquidity": [],
            "unswept_liquidity": [],
            "narrative": "No sweep needed for continuation"
        },
        "displacement_assessment": {
            "direction": "bullish",
            "quality": "clean",
            "structure_broken": True,
            "summary": "Displacement looks clean"
        },
        "active_poi": {
            "poi_id": "fvg_1",
            "price_low": 4051.0,
            "price_high": 4055.0,
            "summary": "Active demand POI"
        },
        "entry_plan": {
            "entry_ready": True,
            "entry_price": 4053.0,
            "mapped_entry_price": 4053.0,
            "entry_zone_low": 4051.0,
            "entry_zone_high": 4055.0,
            "entry_anchor": "fvg_1",
            "evidence_object_ids": ["fvg_1"],
            "summary": "Limit buy"
        },
        "stop_loss_plan": {
            "stop_price": 4050.0,
            "mapped_stop_price": 4050.0,
            "stop_anchor": "range_low",
            "structural_invalidation_price": 4050.0,
            "evidence_object_ids": ["range_low"],
            "summary": "Below range low"
        },
        "target_plan": {
            "targets": [
                {"price": 4062.0, "mapped_target_price": 4062.0, "target_anchor": "target_1", "label": "BSL Target", "reason": "BSL", "evidence_object_ids": ["target_1"]}
            ],
            "summary": "Immediate target"
        },
        "rr_status": {
            "rr": 0.5,  # Bad RR (< 3.0)
            "minimum_rr": 3.0,
            "pass_rr": False,
            "notes": "Low R:R"
        },
        "invalidation": {
            "invalidation_price": 4050.0,
            "mapped_invalidation_price": 4050.0,
            "invalidation_anchor": "range_low",
            "evidence_object_ids": ["range_low"],
            "condition": "Price breaks range low"
        },
        "annotation_plan": {
            "chart_template": "trade_plan_chart",
            "show_trade_box": True,
            "reasoning_order": [
                "daily_context",
                "4h_context",
                "1h_context",
                "active_range",
                "premium_discount",
                "obvious_liquidity",
                "swept_liquidity",
                "displacement_quality",
                "active_poi",
                "entry_model",
                "entry_readiness",
                "structural_invalidation",
                "model_completion_liquidity_target",
                "rr_minimum_three",
                "final_state"
            ]
        },
        "final_thesis": "Thesis details"
    }

    decision = AISMCDecision.model_validate(raw_decision)
    # Mock evidence pack with correct active range authority
    evidence_pack = {
        "active_range_authority": {
            "selected_range": {
                "range_high": 4095.0,
                "range_low": 4050.0,
                "direction": "bullish"
            }
        },
        "detector_candidates": {
            "15m": {
                "pois": [{"object_id": "fvg_1", "price_low": 4051.0, "price_high": 4055.0}],
                "structure_breaks": [{"object_id": "break_1", "direction": "bullish"}],
                "fvgs": [{"object_id": "fvg_1", "direction": "bullish"}],
                "liquidity_levels": [{"price": 4062.0, "object_id": "target_1"}]
            }
        }
    }

    result = validate_ai_smc_decision(decision, evidence_pack)
    assert result.smc_model_validity == "valid"
    assert result.trade_plan_validity == "failed"
    assert "validation_message" in result.official_decision
    assert result.official_decision["validation_message"] == "SMC thesis valid, but trade plan rejected by user RR profile."


def test_reversal_requires_sweep():
    # Setup a decision that is a reversal, but claims no swept liquidity
    raw_decision = {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": "BTCUSDT",
        "official_state": "TRADE_PLAN_READY",
        "setup_grade": "A",
        "direction": "bullish",
        "setup_model": "bullish_reversal_choch",  # Reversal model!
        "bias_summary": {
            "daily": "bullish",
            "4h": "bullish",
            "1h": "bullish",
            "final_bias": "bullish",
            "evidence": []
        },
        "active_range": {
            "timeframe": "15m",
            "high": 4095.0,
            "low": 4050.0,
            "equilibrium": 4072.5,
            "price_location": "discount",
            "source": "active_range_authority"
        },
        "liquidity_story": {
            "obvious_liquidity": [],
            "swept_liquidity": [],  # Empty swept liquidity!
            "unswept_liquidity": [],
            "narrative": "Reversal without sweep"
        },
        "displacement_assessment": {
            "direction": "bullish",
            "quality": "clean",
            "structure_broken": True,
            "summary": "Displacement looks clean"
        },
        "active_poi": {
            "poi_id": "fvg_1",
            "price_low": 4051.0,
            "price_high": 4055.0,
            "summary": "Active demand POI"
        },
        "entry_plan": {
            "entry_ready": True,
            "entry_price": 4058.0,
            "entry_zone_low": 4055.0,
            "entry_zone_high": 4060.0,
            "summary": "Limit buy"
        },
        "stop_loss_plan": {
            "stop_price": 4050.0,
            "structural_invalidation_price": 4050.0,
            "summary": "Below range low"
        },
        "target_plan": {
            "targets": [
                {"price": 4090.0, "label": "BSL Target", "reason": "BSL"}
            ],
            "summary": "Immediate target"
        },
        "rr_status": {
            "rr": 4.0,
            "minimum_rr": 3.0,
            "pass_rr": True,
            "notes": "Good R:R"
        },
        "invalidation": {
            "invalidation_price": 4050.0,
            "condition": "Price breaks range low"
        },
        "annotation_plan": {
            "chart_template": "trade_plan_chart",
            "show_trade_box": True,
            "reasoning_order": [
                "daily_context",
                "4h_context",
                "1h_context",
                "active_range",
                "premium_discount",
                "obvious_liquidity",
                "swept_liquidity",
                "displacement_quality",
                "active_poi",
                "entry_model",
                "entry_readiness",
                "structural_invalidation",
                "model_completion_liquidity_target",
                "rr_minimum_three",
                "final_state"
            ]
        },
        "final_thesis": "Thesis details"
    }

    decision = AISMCDecision.model_validate(raw_decision)
    evidence_pack = {
        "active_range_authority": {
            "selected_range": {
                "range_high": 4095.0,
                "range_low": 4050.0,
                "direction": "bullish"
            }
        },
        "detector_candidates": {
            "15m": {
                "pois": [{"poi_id": "fvg_1", "price_low": 4051.0, "price_high": 4055.0}],
                "structure_breaks": [{"object_id": "break_1", "direction": "bullish"}],
                "fvgs": [{"object_id": "fvg_1", "direction": "bullish"}],
                "liquidity_levels": [{"price": 4090.0, "id": "target_1"}]
            }
        }
    }

    result = validate_ai_smc_decision(decision, evidence_pack)
    assert result.smc_model_validity == "invalid"
    assert "reversal_requires_sweep" in [issue.code for issue in result.issues]


def test_ny_close_daily_resampling():
    # Setup dummy 15m candles covering a timezone shift boundary (e.g. 17:00 Eastern on June 28)
    # June 28, 2026 is a Sunday (US/Eastern is daylight saving, meaning UTC-4)
    # 17:00 Eastern on June 28 is 21:00 UTC.
    data = [
        {"timestamp": "2026-06-28T20:45:00", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1.0},
        # This candle is the last of the previous daily session:
        {"timestamp": "2026-06-28T20:59:59", "open": 11.0, "high": 12.0, "low": 11.0, "close": 11.0, "volume": 1.0},
        # This candle starts the new daily session (17:00 Eastern / 21:00 UTC):
        {"timestamp": "2026-06-28T21:00:00", "open": 20.0, "high": 25.0, "low": 20.0, "close": 21.0, "volume": 1.0},
        {"timestamp": "2026-06-28T21:15:00", "open": 21.0, "high": 21.0, "low": 19.0, "close": 19.0, "volume": 1.0},
    ]
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Resample to NY Close daily
    resampled = resample_to_ny_close_daily(df)
    
    # Should produce 2 candles (one ending at 21:00 UTC on June 28, one starting at 21:00 UTC on June 28)
    assert len(resampled) == 2
    # The first daily candle starts at 17:00 Eastern on the previous day. Its timestamp in UTC is 2026-06-27T21:00:00
    assert resampled.iloc[0]["timestamp"].isoformat() == "2026-06-27T21:00:00"
    # The second daily candle starts at 17:00 Eastern on June 28. Its timestamp in UTC is 2026-06-28T21:00:00
    assert resampled.iloc[1]["timestamp"].isoformat() == "2026-06-28T21:00:00"
    
    # Check OHLC math
    # Candle 0 high covers timestamps before 21:00 UTC: high should be 12.0
    assert resampled.iloc[0]["high"] == 12.0
    # Candle 1 covers timestamps from 21:00 UTC onwards: open = 20.0, high = 25.0, low = 19.0, close = 19.0
    assert resampled.iloc[1]["open"] == 20.0
    assert resampled.iloc[1]["high"] == 25.0
    assert resampled.iloc[1]["low"] == 19.0
    assert resampled.iloc[1]["close"] == 19.0


@pytest.mark.parametrize(
    "resampler",
    [resample_to_ny_close_daily, resample_to_ny_close_daily_canonical],
)
def test_ny_close_daily_resampling_keeps_17_wall_clock_across_spring_dst(resampler):
    frame = pd.DataFrame(
        [
            {"timestamp": "2026-03-07T22:00:00Z", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
            {"timestamp": "2026-03-08T20:00:00Z", "open": 10, "high": 12, "low": 8, "close": 11, "volume": 1},
            {"timestamp": "2026-03-08T21:00:00Z", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 1},
        ]
    )

    result = resampler(frame)

    assert result["timestamp"].tolist() == [
        pd.Timestamp("2026-03-07T22:00:00"),
        pd.Timestamp("2026-03-08T21:00:00"),
    ]
    assert result["_close_visible_at"].tolist() == [
        pd.Timestamp("2026-03-08T21:00:00"),
        pd.Timestamp("2026-03-09T21:00:00"),
    ]
