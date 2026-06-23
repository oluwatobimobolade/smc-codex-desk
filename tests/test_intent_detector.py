"""Unit tests for smc_desk.intent_detector."""
from __future__ import annotations

import unittest

from smc_desk.intent_detector import (
    IntentDetector,
    MarketContext,
    MarketIntent,
)
from smc_desk.sequence_memory import (
    BarSnapshot,
    EpisodeEvent,
    EpisodeEventType,
    EpisodeType,
    MarketEpisode,
    SequenceMemory,
)


class IntentDetectorTests(unittest.TestCase):
    def _make_trap_sequence(self) -> SequenceMemory:
        """Build a rally -> trap -> drop sequence in memory."""
        mem = SequenceMemory()
        # Rally
        for i in range(8):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0 + i * 0.5, 100.5 + i * 0.5, 99.5 + i * 0.5, 100.3 + i * 0.5, 1.0
            ))
        # Trap/reversal
        mem.process_bar(BarSnapshot(8, "t8", 103.5, 104.5, 103.0, 104.0, 2.0))
        mem.process_bar(BarSnapshot(9, "t9", 104.0, 105.0, 102.0, 102.5, 3.0))
        mem.process_bar(BarSnapshot(10, "t10", 102.5, 103.0, 100.0, 100.5, 3.0))
        # Drop
        for i in range(3):
            mem.process_bar(BarSnapshot(
                11 + i, f"t{11 + i}", 100.5 - i * 0.5, 100.5 - i * 0.5, 99.5 - i * 0.5, 99.8 - i * 0.5, 1.0
            ))
        return mem

    def test_detects_distribution_from_rally_trap_drop(self) -> None:
        mem = self._make_trap_sequence()
        detector = IntentDetector()
        result = detector.detect_intent(mem)
        self.assertEqual(result.primary_intent, MarketIntent.SMART_MONEY_DISTRIBUTING)
        self.assertGreater(result.confidence, 0.0)

    def test_visual_spike_trap_triggers_bull_trap(self) -> None:
        mem = SequenceMemory()
        for i in range(10):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0, 101.0, 99.0, 100.5, 1.0
            ))
        detector = IntentDetector()
        visual_patterns = [
            {
                "pattern_type": "vertical_spike_trap",
                "direction": "bearish",
                "confidence": 0.92,
                "invalidates_bias": "bullish",
            }
        ]
        result = detector.detect_intent(mem, visual_patterns=visual_patterns)
        self.assertEqual(result.primary_intent, MarketIntent.BULL_TRAP)

    def test_news_event_takes_priority(self) -> None:
        mem = self._make_trap_sequence()
        detector = IntentDetector()
        context = MarketContext(minutes_to_next_major_news=15.0)
        result = detector.detect_intent(mem, context=context)
        self.assertEqual(result.primary_intent, MarketIntent.NEWS_EVENT_DISTORTION)

    def test_active_trap_yields_chop(self) -> None:
        mem = SequenceMemory()
        ep = MarketEpisode("ep1", EpisodeType.TRAP, 0, 100.0)
        mem.episodes.append(ep)
        mem.active_episode = ep
        detector = IntentDetector()
        result = detector.detect_intent(mem)
        self.assertEqual(result.primary_intent, MarketIntent.CHOP)

    def test_result_serialization(self) -> None:
        mem = self._make_trap_sequence()
        detector = IntentDetector()
        result = detector.detect_intent(mem)
        payload = result.to_dict()
        self.assertIn("primary_intent", payload)
        self.assertIn("all_scores", payload)
        self.assertIn("reasoning", payload)


class MarketContextTests(unittest.TestCase):
    def test_default_context(self) -> None:
        ctx = MarketContext()
        self.assertEqual(ctx.timeframe, "15m")
        self.assertIsNone(ctx.minutes_to_next_major_news)


if __name__ == "__main__":
    unittest.main()
