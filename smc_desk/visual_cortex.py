"""EXPERIMENTAL — SHADOW MODE ONLY. Computer-vision pattern detection for financial charts.

The Visual Cortex analyzes rendered chart images to detect patterns that are
visually salient to human traders but not explicitly present in OHLCV rows:
vertical spikes, failed breakouts, wick rejections, and shape-based traps.

Design principles:
- Pixel input is evidence, not truth. Every detection must be cross-checkable
  against OHLCV data when available.
- Deterministic: same image -> same patterns (modulo rendering noise).
- Modular: pattern detectors are registered plugins; new patterns can be added
  without changing the core pipeline.
- Observability-only by default: the cortex reports patterns; it does not
  originate tradeable prices or override the engine on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

import cv2
import numpy as np


@dataclass
class VisualPattern:
    """A pattern detected in a chart image."""

    pattern_type: str
    confidence: float  # 0.0 to 1.0
    bounding_box: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels
    direction: str  # bullish, bearish, neutral
    start_bar_index: int = 0
    end_bar_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    invalidates_bias: Optional[str] = None  # If set, which bias this pattern kills

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "confidence": round(self.confidence, 4),
            "bounding_box": self.bounding_box,
            "direction": self.direction,
            "start_bar_index": self.start_bar_index,
            "end_bar_index": self.end_bar_index,
            "metadata": self.metadata,
            "invalidates_bias": self.invalidates_bias,
        }


class VisualPatternDetector(Protocol):
    """Plugin interface for pattern detectors."""

    name: str

    def detect(
        self,
        image: np.ndarray,
        bar_regions: list[tuple[int, int, int, int]],
        price_axis: PriceAxis,
    ) -> list[VisualPattern]:
        ...


@dataclass
class PriceAxis:
    """Maps pixel y-coordinates to price values for a rendered chart."""

    top_price: float
    bottom_price: float
    image_height: int
    margin_top: int = 0
    margin_bottom: int = 0

    def pixel_to_price(self, y: int) -> float:
        """Convert pixel y coordinate to price."""
        plot_height = self.image_height - self.margin_top - self.margin_bottom
        if plot_height <= 0:
            return self.bottom_price
        y_plot = np.clip(y, self.margin_top, self.image_height - self.margin_bottom)
        frac = (y_plot - self.margin_top) / plot_height
        return self.top_price + frac * (self.bottom_price - self.top_price)

    def price_to_pixel(self, price: float) -> int:
        """Convert price to pixel y coordinate."""
        plot_height = self.image_height - self.margin_top - self.margin_bottom
        if self.bottom_price == self.top_price:
            return self.margin_top + plot_height // 2
        frac = (price - self.top_price) / (self.bottom_price - self.top_price)
        frac = np.clip(frac, 0.0, 1.0)
        return int(self.margin_top + frac * plot_height)


@dataclass
class VisualCortexConfig:
    """Configuration for chart rendering and detection."""

    # Image dimensions
    width: int = 1920
    height: int = 1080
    margin_top: int = 40
    margin_bottom: int = 40
    margin_left: int = 60
    margin_right: int = 60

    # Candle rendering
    candle_width: int = 4
    wick_width: int = 1

    # Colors (BGR for OpenCV)
    bullish_color: tuple[int, int, int] = (128, 255, 0)
    bearish_color: tuple[int, int, int] = (80, 80, 255)
    background_color: tuple[int, int, int] = (25, 15, 15)
    grid_color: tuple[int, int, int] = (57, 46, 42)
    equilibrium_color: tuple[int, int, int] = (134, 134, 134)

    # Detection thresholds
    spike_min_candles: int = 2
    spike_max_candles: int = 4
    spike_min_vertical_angle: float = 35.0  # degrees
    spike_min_height_px: int = 120
    failed_breakout_lookforward: int = 5
    failed_breakout_min_reclaim_bars: int = 3


class VerticalSpikeDetector:
    """Detects steep price spikes over few candles followed by immediate reversal.

    Uses rendered candle geometry (bar_regions) rather than pure pixel Hough
    transforms, because a trading "spike" is a steep move over few bars, not a
    literally vertical line. The image is still the input; the detector uses the
    known candle layout for robust, deterministic measurement.
    """

    name = "vertical_spike"

    def __init__(self, config: VisualCortexConfig):
        self.config = config

    def detect(
        self,
        image: np.ndarray,
        bar_regions: list[tuple[int, int, int, int]],
        price_axis: PriceAxis,
    ) -> list[VisualPattern]:
        patterns: list[VisualPattern] = []
        n = len(bar_regions)
        if n < self.config.spike_min_candles + 2:
            return patterns

        cfg = self.config
        # Use bar centers and body centers for measurement
        centers = [(left + right) // 2 for (left, _, right, _) in bar_regions]
        # top/bottom are full candle extremes; approximate body center as midpoint
        body_centers = [(top + bottom) // 2 for (_, top, _, bottom) in bar_regions]

        for start_bar in range(n - cfg.spike_min_candles):
            for end_bar in range(
                start_bar + cfg.spike_min_candles - 1,
                min(start_bar + cfg.spike_max_candles, n - 1),
            ):
                spike_candles = end_bar - start_bar + 1
                start_px = body_centers[start_bar]
                end_px = body_centers[end_bar]
                spike_top_px = min(body_centers[start_bar : end_bar + 1])
                spike_bottom_px = max(body_centers[start_bar : end_bar + 1])
                spike_height_px = spike_bottom_px - spike_top_px
                spike_width_px = centers[end_bar] - centers[start_bar]
                if spike_width_px <= 0:
                    continue

                # Steepness: height/width ratio (tangent of angle from horizontal)
                if spike_height_px < cfg.spike_min_height_px:
                    continue
                steepness = spike_height_px / spike_width_px
                angle = np.arctan(steepness) * 180 / np.pi
                if angle < cfg.spike_min_vertical_angle:
                    continue

                # Determine spike direction from price movement
                direction_px = end_px - start_px
                if direction_px == 0:
                    continue
                spike_direction = "up" if direction_px < 0 else "down"

                # Check for immediate reversal after the spike
                reversal = self._check_reversal(
                    body_centers, bar_regions, end_bar, spike_direction, spike_top_px, spike_bottom_px
                )
                if not reversal:
                    continue

                pattern_direction = "bearish" if spike_direction == "up" else "bullish"
                patterns.append(
                    VisualPattern(
                        pattern_type="vertical_spike_trap",
                        confidence=min(0.95, 0.65 + 0.1 * (spike_candles - 1)),
                        bounding_box=(
                            bar_regions[start_bar][0],
                            spike_top_px,
                            bar_regions[end_bar][2],
                            spike_bottom_px,
                        ),
                        direction=pattern_direction,
                        start_bar_index=start_bar,
                        end_bar_index=end_bar,
                        metadata={
                            "spike_height_px": int(spike_height_px),
                            "candles_in_spike": spike_candles,
                            "angle_degrees": round(float(angle), 1),
                            "reversal_bars": reversal,
                            "reversal_strength": round(min(1.0, reversal / 5.0), 3),
                            "time_to_reverse_bars": reversal,
                        },
                        invalidates_bias="bullish" if pattern_direction == "bearish" else "bearish",
                    )
                )

        return self._deduplicate_patterns(patterns)

    def _check_reversal(
        self,
        body_centers: list[int],
        bar_regions: list[tuple[int, int, int, int]],
        spike_end_bar: int,
        spike_direction: str,
        spike_top_px: int,
        spike_bottom_px: int,
    ) -> int:
        """Return number of post-spike bars moving opposite direction, or 0 if none."""
        lookforward = min(
            self.config.failed_breakout_lookforward,
            len(bar_regions) - spike_end_bar - 1,
        )
        if lookforward < 2:
            return 0

        count = 0
        for i in range(1, lookforward + 1):
            idx = spike_end_bar + i
            center = body_centers[idx]
            if spike_direction == "up":
                # Reversal is down: body center below spike bottom-ish
                if center > spike_bottom_px + 5:
                    count += 1
                else:
                    break
            else:
                if center < spike_top_px - 5:
                    count += 1
                else:
                    break

        return count if count >= 2 else 0

    def _deduplicate_patterns(
        self, patterns: list[VisualPattern]
    ) -> list[VisualPattern]:
        if not patterns:
            return patterns
        sorted_patterns = sorted(patterns, key=lambda p: p.confidence, reverse=True)
        kept: list[VisualPattern] = []
        for p in sorted_patterns:
            overlap = False
            for k in kept:
                if self._iou(p.bounding_box, k.bounding_box) > 0.5:
                    overlap = True
                    break
            if not overlap:
                kept.append(p)
        return kept

    @staticmethod
    def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_y = max(0, min(ay2, by2) - max(ay1, by1))
        inter = inter_x * inter_y
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0


class FailedBreakoutDetector:
    """Detects price wicking beyond a level then closing back inside (bull/bear trap)."""

    name = "failed_breakout"

    def __init__(self, config: VisualCortexConfig):
        self.config = config

    def detect(
        self,
        image: np.ndarray,
        bar_regions: list[tuple[int, int, int, int]],
        price_axis: PriceAxis,
    ) -> list[VisualPattern]:
        """Detect failed breakouts against recent swing highs/lows visible in the chart.

        This detector uses rendered candle geometry only. In practice it should be
        combined with OHLCV-derived levels (e.g., equal highs) for precision.
        """
        patterns: list[VisualPattern] = []
        if len(bar_regions) < 5:
            return patterns

        # Identify candidate resistance/support levels from clusters of wick extremes
        # For simplicity, scan each candle and look for wicks that extend far beyond
        # neighbors, then check if subsequent candles fail to follow through.
        for i, region in enumerate(bar_regions[:-3]):
            left, top, right, bottom = region
            candle_center_x = (left + right) // 2
            # Wick above body
            body_top = min(top, bottom)
            body_bottom = max(top, bottom)

            # Find wick pixels above the body
            # We cannot reliably distinguish wick from body without color/model, so
            # we use the full candle range and compare to neighbors.
            neighbors = bar_regions[max(0, i - 3) : i]
            if not neighbors:
                continue
            neighbor_highs = [min(n[1], n[3]) for n in neighbors]
            local_resistance = min(neighbor_highs)

            # Bullish failed breakout: candle wicks above local resistance, body below
            if body_top < local_resistance - 5:  # body below resistance
                # Check subsequent candles close below resistance
                subsequent = bar_regions[i + 1 : i + 1 + self.config.failed_breakout_lookforward]
                if subsequent and all(
                    min(s[1], s[3]) > local_resistance - 3 for s in subsequent[:3]
                ):
                    patterns.append(
                        VisualPattern(
                            pattern_type="failed_breakout",
                            confidence=0.75,
                            bounding_box=(left, top, right, bottom),
                            direction="bearish",
                            start_bar_index=i,
                            end_bar_index=i,
                            metadata={
                                "local_resistance_px": int(local_resistance),
                                "bars_to_fail": 3,
                            },
                            invalidates_bias="bullish",
                        )
                    )

            # Bearish failed breakout symmetric
            neighbor_lows = [max(n[1], n[3]) for n in neighbors]
            local_support = max(neighbor_lows)
            if body_bottom > local_support + 5:
                subsequent = bar_regions[i + 1 : i + 1 + self.config.failed_breakout_lookforward]
                if subsequent and all(
                    max(s[1], s[3]) < local_support + 3 for s in subsequent[:3]
                ):
                    patterns.append(
                        VisualPattern(
                            pattern_type="failed_breakout",
                            confidence=0.75,
                            bounding_box=(left, top, right, bottom),
                            direction="bullish",
                            start_bar_index=i,
                            end_bar_index=i,
                            metadata={
                                "local_support_px": int(local_support),
                                "bars_to_fail": 3,
                            },
                            invalidates_bias="bearish",
                        )
                    )

        return VerticalSpikeDetector(self.config)._deduplicate_patterns(patterns)


class VisualCortex:
    """Top-level visual pattern detection pipeline."""

    def __init__(self, config: Optional[VisualCortexConfig] = None):
        self.config = config or VisualCortexConfig()
        self.detectors: list[VisualPatternDetector] = [
            VerticalSpikeDetector(self.config),
            FailedBreakoutDetector(self.config),
        ]

    def register_detector(self, detector: VisualPatternDetector) -> None:
        self.detectors.append(detector)

    def analyze_image(
        self,
        image: np.ndarray,
        bar_regions: Optional[list[tuple[int, int, int, int]]] = None,
        price_axis: Optional[PriceAxis] = None,
    ) -> list[VisualPattern]:
        """Analyze a chart image and return detected visual patterns."""
        if image is None or image.size == 0:
            return []

        if bar_regions is None:
            bar_regions = self._infer_bar_regions(image)

        if price_axis is None:
            price_axis = self._infer_price_axis(image)

        patterns: list[VisualPattern] = []
        for detector in self.detectors:
            patterns.extend(detector.detect(image, bar_regions, price_axis))

        return patterns

    def _infer_bar_regions(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Infer bar pixel regions from a rendered chart.

        Returns list of (left, top, right, bottom) in image coordinates.
        This is a heuristic; for production use, pass regions from the renderer.
        """
        h, w = image.shape[:2]
        plot_left = self.config.margin_left
        plot_right = w - self.config.margin_right
        plot_top = self.config.margin_top
        plot_bottom = h - self.config.margin_bottom
        plot_width = max(1, plot_right - plot_left)

        # Estimate number of candles from candle width
        n_bars = max(1, plot_width // (self.config.candle_width + 1))
        step = plot_width / n_bars

        regions: list[tuple[int, int, int, int]] = []
        for i in range(n_bars):
            left = int(plot_left + i * step)
            right = int(left + self.config.candle_width)
            regions.append((left, plot_top, right, plot_bottom))
        return regions

    def _infer_price_axis(self, image: np.ndarray) -> PriceAxis:
        """Infer price axis from image. Defaults to normalized 0..1 range."""
        h = image.shape[0]
        return PriceAxis(
            top_price=1.0,
            bottom_price=0.0,
            image_height=h,
            margin_top=self.config.margin_top,
            margin_bottom=self.config.margin_bottom,
        )


def render_chart_for_visual_cortex(
    ohlcv: list[dict[str, float]],
    config: Optional[VisualCortexConfig] = None,
    price_range: Optional[tuple[float, float]] = None,
) -> tuple[np.ndarray, list[tuple[int, int, int, int]], PriceAxis]:
    """Render a minimal OHLCV chart optimized for the Visual Cortex.

    Returns (image, bar_regions, price_axis).
    """
    cfg = config or VisualCortexConfig()
    img = np.full((cfg.height, cfg.width, 3), cfg.background_color, dtype=np.uint8)

    plot_left = cfg.margin_left
    plot_right = cfg.width - cfg.margin_right
    plot_top = cfg.margin_top
    plot_bottom = cfg.height - cfg.margin_bottom

    highs = [b["high"] for b in ohlcv]
    lows = [b["low"] for b in ohlcv]
    if price_range is None:
        top_price = max(highs)
        bottom_price = min(lows)
        pad = (top_price - bottom_price) * 0.05
        top_price += pad
        bottom_price -= pad
    else:
        top_price, bottom_price = price_range

    price_axis = PriceAxis(
        top_price=top_price,
        bottom_price=bottom_price,
        image_height=cfg.height,
        margin_top=cfg.margin_top,
        margin_bottom=cfg.margin_bottom,
    )

    n_bars = len(ohlcv)
    plot_width = plot_right - plot_left
    step = plot_width / max(1, n_bars)

    bar_regions: list[tuple[int, int, int, int]] = []

    for i, bar in enumerate(ohlcv):
        left = int(plot_left + i * step)
        right = int(left + cfg.candle_width)
        center_x = (left + right) // 2

        y_open = price_axis.price_to_pixel(bar["open"])
        y_close = price_axis.price_to_pixel(bar["close"])
        y_high = price_axis.price_to_pixel(bar["high"])
        y_low = price_axis.price_to_pixel(bar["low"])

        body_top = min(y_open, y_close)
        body_bottom = max(y_open, y_close)
        body_bottom = max(body_bottom, body_top + 1)  # ensure visible body

        color = cfg.bullish_color if bar["close"] >= bar["open"] else cfg.bearish_color

        # Wick
        cv2.line(img, (center_x, y_high), (center_x, y_low), color, cfg.wick_width)
        # Body
        cv2.rectangle(img, (left, body_top), (right, body_bottom), color, -1)

        bar_regions.append((left, min(y_high, y_low), right, max(y_high, y_low)))

    return img, bar_regions, price_axis
