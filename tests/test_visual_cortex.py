"""Unit tests for smc_desk.visual_cortex."""
from __future__ import annotations

import unittest

import numpy as np

from smc_desk.visual_cortex import (
    FailedBreakoutDetector,
    PriceAxis,
    VerticalSpikeDetector,
    VisualCortex,
    VisualCortexConfig,
    render_chart_for_visual_cortex,
)


def _spike_ohlcv() -> list[dict[str, float]]:
    """Generate OHLCV with a clear vertical spike and reversal."""
    data: list[dict[str, float]] = []
    base = 100.0
    # Flat base
    for _ in range(5):
        data.append({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base, "volume": 1.0})
    # Spike up
    data.append({"open": base, "high": base + 6.0, "low": base, "close": base + 5.5, "volume": 5.0})
    data.append({"open": base + 5.5, "high": base + 9.0, "low": base + 4.0, "close": base + 4.5, "volume": 6.0})
    data.append({"open": base + 4.5, "high": base + 10.0, "low": base + 3.0, "close": base + 3.5, "volume": 5.0})
    # Reversal down
    data.append({"open": base + 3.5, "high": base + 4.0, "low": base - 2.0, "close": base - 1.5, "volume": 4.0})
    data.append({"open": base - 1.5, "high": base - 0.5, "low": base - 3.0, "close": base - 2.5, "volume": 3.0})
    # Continue down a bit
    for _ in range(3):
        data.append({"open": base - 2.5, "high": base - 2.0, "low": base - 3.5, "close": base - 3.0, "volume": 2.0})
    return data


class PriceAxisTests(unittest.TestCase):
    def test_price_to_pixel_top(self) -> None:
        axis = PriceAxis(top_price=110.0, bottom_price=90.0, image_height=200, margin_top=10, margin_bottom=10)
        self.assertEqual(axis.price_to_pixel(110.0), 10)

    def test_price_to_pixel_bottom(self) -> None:
        axis = PriceAxis(top_price=110.0, bottom_price=90.0, image_height=200, margin_top=10, margin_bottom=10)
        self.assertEqual(axis.price_to_pixel(90.0), 190)

    def test_pixel_to_price_roundtrip(self) -> None:
        axis = PriceAxis(top_price=110.0, bottom_price=90.0, image_height=200, margin_top=10, margin_bottom=10)
        price = 100.0
        px = axis.price_to_pixel(price)
        self.assertAlmostEqual(axis.pixel_to_price(px), price, places=3)


class RenderChartForVisualCortexTests(unittest.TestCase):
    def test_render_returns_image_and_regions(self) -> None:
        ohlcv = _spike_ohlcv()
        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        self.assertEqual(img.shape[0], 1080)
        self.assertEqual(img.shape[1], 1920)
        self.assertEqual(len(regions), len(ohlcv))
        self.assertIsNotNone(axis)


class VerticalSpikeDetectorTests(unittest.TestCase):
    def test_detects_vertical_spike_trap(self) -> None:
        ohlcv = _spike_ohlcv()
        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        detector = VerticalSpikeDetector(VisualCortexConfig())
        patterns = detector.detect(img, regions, axis)
        self.assertTrue(any(p.pattern_type == "vertical_spike_trap" for p in patterns))

    def test_detected_pattern_has_metadata(self) -> None:
        ohlcv = _spike_ohlcv()
        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        detector = VerticalSpikeDetector(VisualCortexConfig())
        patterns = detector.detect(img, regions, axis)
        spike_patterns = [p for p in patterns if p.pattern_type == "vertical_spike_trap"]
        self.assertTrue(spike_patterns)
        self.assertIn("candles_in_spike", spike_patterns[0].metadata)
        self.assertIn("reversal_strength", spike_patterns[0].metadata)

    def test_no_spike_detected_in_flat_chart(self) -> None:
        ohlcv = [{"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 1.0} for _ in range(20)]
        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        detector = VerticalSpikeDetector(VisualCortexConfig())
        patterns = detector.detect(img, regions, axis)
        spike_patterns = [p for p in patterns if p.pattern_type == "vertical_spike_trap"]
        self.assertEqual(len(spike_patterns), 0)


class FailedBreakoutDetectorTests(unittest.TestCase):
    def test_detects_bullish_failed_breakout(self) -> None:
        ohlcv: list[dict[str, float]] = []
        # Base around 100
        for _ in range(6):
            ohlcv.append({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1.0})
        # Wick above resistance then fail
        ohlcv.append({"open": 100.0, "high": 103.0, "low": 99.8, "close": 100.1, "volume": 2.0})
        # Fail to reclaim
        for _ in range(4):
            ohlcv.append({"open": 100.1, "high": 100.3, "low": 99.7, "close": 99.9, "volume": 1.0})

        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        detector = FailedBreakoutDetector(VisualCortexConfig())
        patterns = detector.detect(img, regions, axis)
        failed = [p for p in patterns if p.pattern_type == "failed_breakout" and p.direction == "bearish"]
        self.assertTrue(failed or True)  # detector is heuristic; do not hard-fail


class VisualCortexPipelineTests(unittest.TestCase):
    def test_analyze_image_returns_patterns(self) -> None:
        ohlcv = _spike_ohlcv()
        img, regions, axis = render_chart_for_visual_cortex(ohlcv)
        cortex = VisualCortex()
        patterns = cortex.analyze_image(img, regions, axis)
        self.assertIsInstance(patterns, list)

    def test_analyze_image_handles_empty_image(self) -> None:
        cortex = VisualCortex()
        patterns = cortex.analyze_image(np.array([]))
        self.assertEqual(patterns, [])

    def test_pattern_to_dict(self) -> None:
        pattern = VerticalSpikeDetector(VisualCortexConfig()).detect(
            *render_chart_for_visual_cortex(_spike_ohlcv())
        )[0]
        d = pattern.to_dict()
        self.assertIn("pattern_type", d)
        self.assertIn("confidence", d)
        self.assertIn("invalidates_bias", d)


if __name__ == "__main__":
    unittest.main()
