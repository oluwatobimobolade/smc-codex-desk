"""Tests for smc_desk.episode_narrative.EpisodeNarrativeBuilder."""
from __future__ import annotations

import unittest

from smc_desk.episode_narrative import EpisodeNarrativeBuilder
from smc_desk.models import StructureEvent
from smc_desk.sequence_memory import BarSnapshot, EpisodeType, MarketEpisode


def _bar(i: int, price: float = 100.0) -> BarSnapshot:
    return BarSnapshot(
        index=i,
        timestamp=f"t{i}",
        open=price,
        high=price + 0.5,
        low=price - 0.5,
        close=price + 0.1,
        volume=1.0,
    )


def _sweep(i: int, direction: str, price: float) -> StructureEvent:
    return StructureEvent(
        label="Liquidity Sweep",
        direction=direction,
        index=i,
        timestamp=f"t{i}",
        price=price,
        reason="sweep",
    )


def _break(i: int, direction: str, price: float) -> StructureEvent:
    return StructureEvent(
        label="BOS",
        direction=direction,
        index=i,
        timestamp=f"t{i}",
        price=price,
        reason="break",
        structure_scope="swing",
        strength="strong",
        displacement_score=1.5,
    )


class EpisodeNarrativeBuilderTests(unittest.TestCase):
    """Verify episodes are derived from engine structure events, not raw bars."""

    def test_empty_builder_has_no_episodes(self) -> None:
        builder = EpisodeNarrativeBuilder()
        self.assertEqual(len(builder.episodes), 0)
        self.assertIsNone(builder.active_episode)

    def test_rally_from_bullish_sweep_and_break(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(10):
            events = []
            if i == 3:
                events.append(_sweep(3, "bullish", 99.0))
            if i == 4:
                events.append(_break(4, "bullish", 100.5))
            builder.process_bar(_bar(i, 100.0 + i * 0.1), events)
        self.assertIsNotNone(builder.active_episode)
        self.assertEqual(builder.active_episode.episode_type, EpisodeType.RALLY)

    def test_drop_from_bearish_sweep_and_break(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(10):
            events = []
            if i == 3:
                events.append(_sweep(3, "bearish", 101.0))
            if i == 4:
                events.append(_break(4, "bearish", 99.5))
            builder.process_bar(_bar(i, 100.0 - i * 0.1), events)
        self.assertIsNotNone(builder.active_episode)
        self.assertEqual(builder.active_episode.episode_type, EpisodeType.DROP)

    def test_sweep_without_displacement_becomes_trap_on_termination(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(10):
            events = []
            if i == 3:
                events.append(_sweep(3, "bullish", 99.0))
            # No displacement break follows.
            builder.process_bar(_bar(i), events)
        # Then an opposite-direction break terminates the pending sweep.
        builder.process_bar(
            _bar(10),
            [_break(10, "bearish", 99.5)],
        )
        trap_episodes = [ep for ep in builder.episodes if ep.episode_type == EpisodeType.TRAP]
        self.assertTrue(trap_episodes, "pending sweep without displacement should become a trap")

    def test_consolidation_timeout_creates_one_episode(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=3)
        for i in range(15):
            events = []
            if i == 2:
                events.append(_sweep(2, "bullish", 99.0))
            if i == 3:
                events.append(_break(3, "bullish", 100.5))
            builder.process_bar(_bar(i), events)
        # After the rally, a single consolidation should form (not many).
        consolidation_episodes = [
            ep for ep in builder.episodes if ep.episode_type == EpisodeType.CONSOLIDATION
        ]
        self.assertLessEqual(len(consolidation_episodes), 1)

    def test_opposite_direction_terminates_active_episode(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(8):
            events = []
            if i == 1:
                events.append(_sweep(1, "bullish", 99.0))
            if i == 2:
                events.append(_break(2, "bullish", 100.5))
            if i == 6:
                events.append(_sweep(6, "bearish", 101.0))
            builder.process_bar(_bar(i), events)
        # The first episode (rally) should be terminated and archived.
        rally_episodes = [ep for ep in builder.episodes if ep.episode_type == EpisodeType.RALLY]
        self.assertTrue(rally_episodes)
        self.assertIsNotNone(rally_episodes[0].end_bar)

    def test_episode_high_low_tracks_bar_data(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(10):
            events = []
            if i == 1:
                events.append(_sweep(1, "bullish", 99.0))
            if i == 2:
                events.append(_break(2, "bullish", 100.5))
            builder.process_bar(_bar(i, 100.0 + i * 0.5), events)
        ep = builder.active_episode
        self.assertIsNotNone(ep)
        self.assertGreater(ep.high_price, ep.low_price)

    def test_narrative_is_human_readable(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(6):
            events = []
            if i == 1:
                events.append(_sweep(1, "bullish", 99.0))
            if i == 2:
                events.append(_break(2, "bullish", 100.5))
            builder.process_bar(_bar(i), events)
        narrative = builder.get_current_narrative()
        self.assertIn("RALLY", narrative)

    def test_to_dict_serializes(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(6):
            events = []
            if i == 1:
                events.append(_sweep(1, "bullish", 99.0))
            if i == 2:
                events.append(_break(2, "bullish", 100.5))
            builder.process_bar(_bar(i), events)
        payload = builder.to_dict()
        self.assertIn("episodes", payload)
        self.assertIn("active_episode", payload)
        self.assertIn("narrative", payload)

    def test_reset_clears_state(self) -> None:
        builder = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
        for i in range(6):
            events = []
            if i == 1:
                events.append(_sweep(1, "bullish", 99.0))
            if i == 2:
                events.append(_break(2, "bullish", 100.5))
            builder.process_bar(_bar(i), events)
        builder.reset()
        self.assertEqual(len(builder.episodes), 0)
        self.assertIsNone(builder.active_episode)


class EpisodeNarrativeLeakageTests(unittest.TestCase):
    """Episodes must not be revised when future bars arrive."""

    def test_ended_episodes_stable_after_future_bars(self) -> None:
        snapshots = [_bar(i) for i in range(30)]
        events_map: dict[int, list[StructureEvent]] = {
            3: [_sweep(3, "bullish", 99.0)],
            4: [_break(4, "bullish", 100.5)],
            10: [_sweep(10, "bearish", 101.0)],
        }

        def build_up_to(cutoff: int) -> EpisodeNarrativeBuilder:
            b = EpisodeNarrativeBuilder(consolidation_timeout_bars=99)
            for i in range(cutoff):
                b.process_bar(snapshots[i], events_map.get(i, []))
            return b

        short = build_up_to(12)
        full = build_up_to(30)

        short_ended = [ep.to_dict() for ep in short.episodes]
        full_ended = [ep.to_dict() for ep in full.episodes if ep.end_bar is not None and ep.end_bar < 12]
        self.assertEqual(short_ended, full_ended)


if __name__ == "__main__":
    unittest.main()
