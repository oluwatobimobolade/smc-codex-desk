"""Unit tests for smc_desk.fusion_engine."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from smc_desk.engine import analyze_dataframe
from smc_desk.fusion_engine import FusionEngine, FusionEngineConfig
from smc_desk.intent_detector import IntentDetector, MarketIntent
from smc_desk.rules import RuleConfig
from smc_desk.sequence_memory import BarSnapshot, EpisodeType, MarketEpisode, SequenceMemory


def _make_simple_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"timestamp": "2026-01-01T00:00:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
        {"timestamp": "2026-01-01T00:15:00", "open": 100.5, "high": 101.5, "low": 100.0, "close": 101.0, "volume": 1.0},
        {"timestamp": "2026-01-01T00:30:00", "open": 101.0, "high": 102.0, "low": 100.5, "close": 101.5, "volume": 1.0},
    ])


def _make_bullish_bearish_plans():
    """Return an engine result where bullish is Watch and bearish is Pass."""
    df = _make_simple_df()
    config = RuleConfig()
    result, _ = analyze_dataframe(df, "TEST", "15m", config)
    return result


class FusionEngineTests(unittest.TestCase):
    def test_fusion_without_overrides_keeps_primary_engine_verdict(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())
        fusion = FusionEngine()
        result = fusion.fuse(engine_result, mem)
        self.assertEqual(result.engine_primary_verdict, engine_result.trade_plan.verdict)
        self.assertEqual(result.engine_primary_bias, engine_result.trade_plan.direction)
        self.assertEqual(len(result.overrides), 0)

    def test_intent_modulation_log_only_by_default(self) -> None:
        """Until calibrated, intent is logged but does not change the recommendation."""
        engine_result = _make_bullish_bearish_plans()
        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())

        detector = IntentDetector()
        intent = detector.detect_intent(mem)
        intent.primary_intent = MarketIntent.BULL_TRAP
        intent.confidence = 0.92

        fusion = FusionEngine()
        result = fusion.fuse(engine_result, mem, intent_result=intent)
        # Intent is logged as a conflict but modulation is disabled by default.
        self.assertTrue(any("bull_trap" in c for c in result.conflicts))

    def test_intent_modulation_when_enabled_penalizes_bullish(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        # Ensure both directions are candidates for scoring.
        if engine_result.bullish_plan:
            engine_result.bullish_plan.verdict = "Watch"
        if engine_result.bearish_plan:
            engine_result.bearish_plan.verdict = "Watch"

        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())

        detector = IntentDetector()
        intent = detector.detect_intent(mem)
        intent.primary_intent = MarketIntent.BULL_TRAP
        intent.confidence = 0.92

        with patch("smc_desk.fusion_engine.load_rule_config") as mock_load:
            mock_config = MagicMock()
            mock_config.vision_authority_mode = "veto"
            mock_load.return_value = mock_config
            fusion = FusionEngine(FusionEngineConfig(allow_intent_modulation=True))
            result = fusion.fuse(engine_result, mem, intent_result=intent)
        
        # A BULL_TRAP intent should reduce the bullish score relative to bearish.
        if "bullish" in result.scores and "bearish" in result.scores:
            self.assertLess(
                result.scores["bullish"],
                result.scores["bearish"],
                "bull trap should modulate bullish score below bearish",
            )

    def test_active_trap_downgrades_execute(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        if engine_result.bullish_plan:
            engine_result.bullish_plan.verdict = "Execute"
            engine_result.bullish_plan.setup_grade = "A"

        mem = SequenceMemory()
        mem.active_episode = MarketEpisode("ep1", EpisodeType.TRAP, 0, 100.0)

        with patch("smc_desk.fusion_engine.load_rule_config") as mock_load:
            mock_config = MagicMock()
            mock_config.vision_authority_mode = "veto"
            mock_load.return_value = mock_config
            fusion = FusionEngine()
            result = fusion.fuse(engine_result, mem)
            
        self.assertEqual(result.recommended_verdict, "Watch")
        self.assertTrue(any("trap" in o.reason.lower() for o in result.overrides))

    def test_visual_conflict_is_logged_not_asserted(self) -> None:
        """Visual patterns create conflicts, they do not flip the recommendation."""
        engine_result = _make_bullish_bearish_plans()
        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())

        visual_patterns = [
            {
                "pattern_type": "vertical_spike_trap",
                "confidence": 0.85,
                "direction": "bearish",
                "invalidates_bias": "bullish",
            }
        ]

        fusion = FusionEngine()
        result = fusion.fuse(engine_result, mem, visual_patterns=visual_patterns)
        self.assertTrue(any("visual" in c.lower() for c in result.conflicts))

    def test_confidence_penalized_on_conflict(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        if engine_result.bullish_plan:
            engine_result.bullish_plan.confidence = 0.8
            engine_result.bullish_plan.verdict = "Watch"
        if engine_result.bearish_plan:
            engine_result.bearish_plan.verdict = "Pass"

        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())

        visual_patterns = [
            {
                "pattern_type": "vertical_spike_trap",
                "confidence": 0.85,
                "direction": "bearish",
                "invalidates_bias": "bullish",
            }
        ]

        fusion = FusionEngine(FusionEngineConfig(conflict_confidence_penalty=0.8))
        result = fusion.fuse(engine_result, mem, visual_patterns=visual_patterns)
        self.assertLess(result.fused_confidence, 0.8)

    def test_fusion_result_serializes(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())
        fusion = FusionEngine()
        result = fusion.fuse(engine_result, mem)
        payload = result.to_dict()
        self.assertIn("engine_primary_verdict", payload)
        self.assertIn("recommended_verdict", payload)
        self.assertIn("bullish_plan_summary", payload)
        self.assertIn("bearish_plan_summary", payload)
        self.assertIn("price_sources", payload)
        self.assertIn("contributions", payload)

    def test_price_sources_map_engine_prices(self) -> None:
        engine_result = _make_bullish_bearish_plans()
        mem = SequenceMemory()
        mem.process_dataframe(_make_simple_df())
        fusion = FusionEngine()
        result = fusion.fuse(engine_result, mem)
        # Every price source should be tagged with a direction and be numeric.
        for price, source in result.price_sources.items():
            self.assertTrue(
                source.startswith("bullish") or source.startswith("bearish"),
                f"price {price} source {source!r} missing direction prefix",
            )
            self.assertTrue(
                price.replace(".", "", 1).replace("-", "", 1).isdigit(),
                f"price {price!r} is not numeric",
            )


if __name__ == "__main__":
    unittest.main()
