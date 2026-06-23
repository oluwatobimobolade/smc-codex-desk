"""Unit tests for smc_desk.sequence_memory."""
from __future__ import annotations

import unittest

import pandas as pd

from smc_desk.sequence_memory import (
    BarSnapshot,
    EpisodeEvent,
    EpisodeEventType,
    EpisodeType,
    MarketEpisode,
    SequenceMemory,
    SequenceMemoryConfig,
)


def _make_bars_rally_then_trap() -> pd.DataFrame:
    """Create a synthetic rally -> spike trap -> drop sequence."""
    data: list[dict[str, float]] = []
    base = 100.0
    # Rally phase: gradual climb
    for i in range(10):
        data.append({
            "timestamp": f"2026-01-01T00:{i:02d}:00",
            "open": base + i * 0.5,
            "high": base + i * 0.5 + 0.3,
            "low": base + i * 0.5 - 0.1,
            "close": base + i * 0.5 + 0.2,
            "volume": 100.0,
        })
    # Spike trap: 3 candles shooting up then reversing
    data.extend([
        {"timestamp": "2026-01-01T00:10:00", "open": 105.0, "high": 106.0, "low": 104.9, "close": 105.8, "volume": 200.0},
        {"timestamp": "2026-01-01T00:11:00", "open": 105.8, "high": 108.5, "low": 105.7, "close": 106.2, "volume": 300.0},
        {"timestamp": "2026-01-01T00:12:00", "open": 106.2, "high": 109.0, "low": 105.0, "close": 105.5, "volume": 250.0},
    ])
    # Drop phase
    for i in range(5):
        data.append({
            "timestamp": f"2026-01-01T00:{13 + i:02d}:00",
            "open": 105.5 - i * 0.6,
            "high": 105.5 - i * 0.6 + 0.2,
            "low": 105.5 - i * 0.6 - 0.4,
            "close": 105.5 - i * 0.6 - 0.3,
            "volume": 150.0,
        })
    return pd.DataFrame(data)


class BarSnapshotTests(unittest.TestCase):
    def test_bar_properties_bullish(self) -> None:
        bar = BarSnapshot(index=0, timestamp="t", open=100.0, high=105.0, low=99.0, close=104.0, volume=10.0)
        self.assertEqual(bar.direction, "bullish")
        self.assertEqual(bar.body_size, 4.0)
        self.assertEqual(bar.range, 6.0)
        self.assertEqual(bar.upper_wick, 1.0)
        self.assertEqual(bar.lower_wick, 1.0)

    def test_bar_properties_bearish(self) -> None:
        bar = BarSnapshot(index=0, timestamp="t", open=104.0, high=105.0, low=99.0, close=100.0, volume=10.0)
        self.assertEqual(bar.direction, "bearish")
        self.assertEqual(bar.body_size, 4.0)
        self.assertEqual(bar.upper_wick, 1.0)
        self.assertEqual(bar.lower_wick, 1.0)


class SequenceMemoryInitTests(unittest.TestCase):
    def test_initial_state_is_empty(self) -> None:
        mem = SequenceMemory()
        self.assertIsNone(mem.active_episode)
        self.assertEqual(len(mem.episodes), 0)
        self.assertEqual(len(mem.bars), 0)

    def test_reset_clears_state(self) -> None:
        mem = SequenceMemory()
        df = pd.DataFrame([{
            "timestamp": "t", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0
        }])
        mem.process_dataframe(df)
        mem.reset()
        self.assertIsNone(mem.active_episode)
        self.assertEqual(len(mem.episodes), 0)


class SequenceMemoryEpisodeTests(unittest.TestCase):
    def test_single_bar_is_undefined(self) -> None:
        mem = SequenceMemory()
        mem.process_bar(BarSnapshot(0, "t", 100.0, 101.0, 99.0, 100.5, 1.0))
        self.assertIsNotNone(mem.active_episode)
        self.assertEqual(mem.active_episode.episode_type, EpisodeType.UNDEFINED)

    def test_rally_detected_on_up_move(self) -> None:
        mem = SequenceMemory()
        for i in range(8):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0 + i, 101.0 + i, 99.5 + i, 100.5 + i, 1.0
            ))
        self.assertEqual(mem.active_episode.episode_type, EpisodeType.RALLY)

    def test_drop_detected_on_down_move(self) -> None:
        mem = SequenceMemory()
        for i in range(8):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0 - i, 100.5 - i, 99.0 - i, 99.5 - i, 1.0
            ))
        self.assertEqual(mem.active_episode.episode_type, EpisodeType.DROP)

    def test_50_percent_retrace_terminates_rally(self) -> None:
        mem = SequenceMemory()
        # Rally from 100 to 110
        for i in range(10):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0 + i, 101.0 + i, 99.5 + i, 100.5 + i, 1.0
            ))
        # Retrace below 105 (50%)
        mem.process_bar(BarSnapshot(10, "t10", 109.5, 109.5, 104.0, 104.5, 1.0))
        terminated = list(mem.episodes)
        self.assertTrue(any(ep.episode_type == EpisodeType.RALLY for ep in terminated))
        self.assertIsNotNone(mem.active_episode)

    def test_trap_detected_after_spike(self) -> None:
        df = _make_bars_rally_then_trap()
        mem = SequenceMemory()
        mem.process_dataframe(df)
        episode_types = [ep.episode_type for ep in mem.episodes] + [mem.active_episode.episode_type]
        self.assertIn(EpisodeType.TRAP, episode_types)

    def test_narrative_contains_distribution_inference(self) -> None:
        df = _make_bars_rally_then_trap()
        mem = SequenceMemory()
        mem.process_dataframe(df)
        narrative = mem.get_current_narrative()
        self.assertIn("Distribution", narrative)

    def test_serialization_roundtrip(self) -> None:
        df = _make_bars_rally_then_trap()
        mem = SequenceMemory()
        mem.process_dataframe(df)
        payload = mem.to_dict()
        self.assertIn("episodes", payload)
        self.assertIn("narrative", payload)
        self.assertIsInstance(payload["episode_count"], int)


class EpisodeTerminationTests(unittest.TestCase):
    def test_opposite_displacement_terminates_rally(self) -> None:
        mem = SequenceMemory()
        # Small rally
        for i in range(5):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0 + i * 0.2, 100.5 + i * 0.2, 99.5 + i * 0.2, 100.3 + i * 0.2, 1.0
            ))
        # Big displacement down
        mem.process_bar(BarSnapshot(5, "t5", 101.0, 101.0, 98.0, 98.5, 1.0))
        mem.process_bar(BarSnapshot(6, "t6", 98.5, 99.0, 97.5, 97.8, 1.0))
        terminated = [ep for ep in mem.episodes if ep.episode_type == EpisodeType.RALLY]
        self.assertTrue(terminated)

    def test_timeout_terminates_flat_episode(self) -> None:
        cfg = SequenceMemoryConfig(episode_timeout_bars=10, accumulation_max_range_pct=0.001)
        mem = SequenceMemory(config=cfg)
        for i in range(12):
            mem.process_bar(BarSnapshot(
                i, f"t{i}", 100.0, 100.1, 99.9, 100.0, 1.0
            ))
        self.assertGreater(len(mem.episodes), 0)


class MarketEpisodeTests(unittest.TestCase):
    def test_episode_update_bar_tracks_high_low(self) -> None:
        ep = MarketEpisode("ep1", EpisodeType.RALLY, 0, 100.0)
        ep.update_bar(BarSnapshot(1, "t", 100.0, 105.0, 99.0, 104.0, 1.0))
        self.assertEqual(ep.high_price, 105.0)
        self.assertEqual(ep.low_price, 99.0)

    def test_episode_termination(self) -> None:
        ep = MarketEpisode("ep1", EpisodeType.RALLY, 0, 100.0)
        event = EpisodeEvent(EpisodeEventType.RETRACE_50, 5, "t5", 98.0, "bearish")
        ep.terminate(5, 98.0, event)
        self.assertFalse(ep.is_active)
        self.assertEqual(ep.end_bar, 5)
        self.assertEqual(ep.duration_bars, 5)


if __name__ == "__main__":
    unittest.main()
