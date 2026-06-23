from __future__ import annotations

import unittest

from smc_desk.state_machine import (
    PoiAnchor,
    SetupState,
    StateInput,
    StateMachineConfig,
    advance_setup,
)


def event(bar: int, **changes) -> StateInput:
    values = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "bar_index": bar,
        "timestamp": f"2026-01-01T00:{bar:02d}:00Z",
        "htf_direction": "bullish",
    }
    values.update(changes)
    return StateInput(**values)


POI = PoiAnchor(kind="fvg", low=100.0, high=102.0, source_bar_index=10, score=0.8)


class StateMachineTests(unittest.TestCase):
    def test_records_full_narrative_without_reselecting_the_poi(self) -> None:
        update = advance_setup(event(10, sweep_direction="bullish", sweep_price=99.0), None)
        self.assertEqual(update.display_state, SetupState.SWEEP_DETECTED)

        update = advance_setup(
            event(12, displacement_direction="bullish", displacement_price=104.0, candidate_poi=POI),
            update.active_setup,
        )
        self.assertEqual(update.display_state, SetupState.DISPLACED)
        self.assertEqual(update.active_setup.poi, POI)

        update = advance_setup(event(16, poi_touched=True), update.active_setup)
        self.assertEqual(update.display_state, SetupState.POI_ACTIVE)

        update = advance_setup(event(17, confirmation=True, confirmation_name="research_signature"), update.active_setup)
        self.assertEqual(update.display_state, SetupState.EXECUTE)
        self.assertEqual(update.active_setup.confirmation_name, "research_signature")

    def test_requires_a_poi_on_the_displacement_candle(self) -> None:
        sweep = advance_setup(event(10, sweep_direction="bullish", sweep_price=99.0), None)
        update = advance_setup(
            event(11, displacement_direction="bullish", displacement_price=104.0),
            sweep.active_setup,
        )

        self.assertIsNone(update.active_setup)
        self.assertEqual(update.transition.to_state, SetupState.EXPIRED)
        self.assertEqual(update.transition.reason, "no_eligible_poi_on_displacement")

    def test_same_bar_sweep_and_displacement_preserves_both_transitions(self) -> None:
        update = advance_setup(
            event(
                10,
                sweep_direction="bullish",
                sweep_price=99.0,
                displacement_direction="bullish",
                displacement_price=104.0,
                candidate_poi=POI,
            ),
            None,
        )

        self.assertEqual(update.display_state, SetupState.DISPLACED)
        self.assertEqual([transition.to_state for transition in update.transitions], [SetupState.SWEEP_DETECTED, SetupState.DISPLACED])

    def test_displacement_timeout_is_terminal_and_logged(self) -> None:
        config = StateMachineConfig(displacement_timeout_bars=3)
        sweep = advance_setup(event(10, sweep_direction="bullish", sweep_price=99.0), None, config)
        update = advance_setup(event(14), sweep.active_setup, config)

        self.assertIsNone(update.active_setup)
        self.assertEqual(update.transition.to_state, SetupState.EXPIRED)
        self.assertEqual(update.transition.reason, "displacement_timeout")

    def test_sweep_invalidation_stops_a_displaced_setup(self) -> None:
        sweep = advance_setup(event(10, sweep_direction="bullish", sweep_price=99.0), None)
        displaced = advance_setup(
            event(11, displacement_direction="bullish", displacement_price=104.0, candidate_poi=POI),
            sweep.active_setup,
        )
        update = advance_setup(event(12, sweep_invalidated=True), displaced.active_setup)

        self.assertIsNone(update.active_setup)
        self.assertEqual(update.transition.to_state, SetupState.INVALIDATED)

    def test_rejects_out_of_order_or_cross_symbol_updates(self) -> None:
        sweep = advance_setup(event(10, sweep_direction="bullish", sweep_price=99.0), None)
        with self.assertRaisesRegex(ValueError, "chronological"):
            advance_setup(event(9), sweep.active_setup)
        with self.assertRaisesRegex(ValueError, "symbol/timeframe"):
            advance_setup(event(11, symbol="ETHUSDT"), sweep.active_setup)


if __name__ == "__main__":
    unittest.main()
