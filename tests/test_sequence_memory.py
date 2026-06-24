"""Tests for smc_desk.sequence_memory shared types.

The SequenceMemory class (bar-processor) has been superseded by
EpisodeNarrativeBuilder in smc_desk.episode_narrative. This file
now tests only the shared type definitions: BarSnapshot, EpisodeType,
EpisodeEventType, MarketEpisode, EpisodeEvent.

The episode classification logic is tested in
tests/test_episode_narrative.py.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smc_desk.sequence_memory import (
    BarSnapshot,
    EpisodeEvent,
    EpisodeEventType,
    EpisodeType,
    MarketEpisode,
)


class BarSnapshotTests(unittest.TestCase):
    def test_properties_bullish(self) -> None:
        bar = BarSnapshot(
            index=0, timestamp="t0", open=100.0, high=101.0, low=99.0,
            close=101.0, volume=1.0,
        )
        self.assertEqual(bar.direction, "bullish")
        self.assertEqual(bar.body_size, 1.0)
        self.assertEqual(bar.range, 2.0)
        self.assertEqual(bar.upper_wick, 0.0)  # close at high
        self.assertEqual(bar.lower_wick, 1.0)  # open 100, low 99

    def test_properties_bearish(self) -> None:
        bar = BarSnapshot(
            index=0, timestamp="t0", open=101.0, high=102.0, low=99.0,
            close=99.5, volume=1.0,
        )
        self.assertEqual(bar.direction, "bearish")
        self.assertAlmostEqual(bar.upper_wick, 1.0)  # high 102, body top 101
        self.assertAlmostEqual(bar.lower_wick, 0.5)  # body bottom 99.5, low 99.0


class MarketEpisodeTests(unittest.TestCase):
    def _make_episode(self, episode_type=EpisodeType.RALLY, start_bar=0, end_bar=5) -> MarketEpisode:
        ep = MarketEpisode(
            episode_id="ep_001",
            episode_type=episode_type,
            start_bar=start_bar,
            start_price=100.0,
        )
        ep.end_bar = end_bar
        ep.end_price = 105.0
        ep.high_price = 106.0
        ep.low_price = 99.5
        ep.is_active = False
        return ep

    def test_duration_bars(self) -> None:
        ep = self._make_episode(start_bar=2, end_bar=8)
        self.assertEqual(ep.duration_bars, 6)

    def test_range_pct(self) -> None:
        ep = self._make_episode()
        self.assertAlmostEqual(ep.range_pct, 0.065, places=3)

    def test_to_dict_serialization(self) -> None:
        ep = self._make_episode()
        ep.key_events.append(EpisodeEvent(
            event_type=EpisodeEventType.DISPLACEMENT,
            bar_index=0, timestamp="t0", price=100.0, direction="bullish",
        ))
        payload = ep.to_dict()
        self.assertEqual(payload["episode_type"], "rally")
        self.assertEqual(payload["start_bar"], 0)
        self.assertEqual(payload["end_bar"], 5)
        self.assertEqual(len(payload["key_events"]), 1)
        self.assertEqual(payload["key_events"][0]["event_type"], "displacement")

    def test_terminate(self) -> None:
        ep = self._make_episode()
        reason = EpisodeEvent(
            event_type=EpisodeEventType.TIMEOUT,
            bar_index=5, timestamp="t5", price=105.0, direction="neutral",
        )
        ep.terminate(5, 105.0, reason)
        self.assertEqual(ep.end_bar, 5)
        self.assertEqual(ep.end_price, 105.0)
        self.assertFalse(ep.is_active)
        self.assertIn(reason, ep.key_events)


class EpisodeTypeTests(unittest.TestCase):
    def test_all_types_present(self) -> None:
        types = {t.value for t in EpisodeType}
        self.assertIn("rally", types)
        self.assertIn("drop", types)
        self.assertIn("consolidation", types)
        self.assertIn("trap", types)
        self.assertIn("accumulation", types)
        self.assertIn("distribution", types)
        self.assertIn("undefined", types)

    def test_event_types_present(self) -> None:
        types = {t.value for t in EpisodeEventType}
        self.assertIn("displacement", types)
        self.assertIn("sweep", types)
        self.assertIn("reversal", types)
        self.assertIn("opposite_displacement", types)
        self.assertIn("retrace_50", types)
        self.assertIn("timeout", types)


if __name__ == "__main__":
    unittest.main()
