"""Context-aware regime classification for SMC perception.

The regime engine does not predict trades. It describes the environment so the
colleague can downgrade or refuse setups when context is unclear.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import mean
from typing import Sequence

from smc_desk.data.schemas import Candle


@dataclass(frozen=True)
class RegimeAssessment:
    structure_regime: str
    volatility_regime: str
    liquidity_regime: str
    confidence: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def should_downgrade(self) -> bool:
        return self.confidence < 0.60

    def to_dict(self) -> dict:
        return {
            "structure_regime": self.structure_regime,
            "volatility_regime": self.volatility_regime,
            "liquidity_regime": self.liquidity_regime,
            "confidence": round(self.confidence, 4),
            "should_downgrade": self.should_downgrade,
            "components": {key: round(value, 4) for key, value in self.components.items()},
            "reasons": list(self.reasons),
        }


def classify_market_regime(candles: Sequence[Candle], *, lookback: int = 96) -> RegimeAssessment:
    """Classify structure, volatility, and liquidity behavior.

    This is deterministic heuristics, not trained prediction. Low-confidence
    classification is an explicit downgrade signal for the decision layer.
    """
    usable = list(candles)[-lookback:]
    if len(usable) < 30:
        confidence = min(0.55, len(usable) / 60)
        return RegimeAssessment(
            structure_regime="transitional",
            volatility_regime="compression",
            liquidity_regime="accumulation",
            confidence=round(confidence, 4),
            components={"sample": confidence, "structure": 0.4, "volatility": 0.4, "liquidity": 0.35},
            reasons=[f"insufficient_regime_history:{len(usable)}_bars"],
        )

    closes = [_float(c.close) for c in usable]
    highs = [_float(c.high) for c in usable]
    lows = [_float(c.low) for c in usable]
    opens = [_float(c.open) for c in usable]
    ranges = [max(h - l, 0.0) for h, l in zip(highs, lows)]
    true_ranges = _true_ranges(usable)

    total_path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    net_move = closes[-1] - closes[0]
    efficiency = abs(net_move) / total_path if total_path else 0.0
    avg_range = mean(ranges) if ranges else 0.0
    slope_norm = abs(net_move) / (avg_range * max(len(closes) ** 0.5, 1.0)) if avg_range else 0.0

    if efficiency >= 0.34 and slope_norm >= 0.65:
        structure_regime = "trending"
        structure_score = min(1.0, 0.55 + efficiency + min(slope_norm, 1.0) * 0.25)
        structure_reason = f"directional_efficiency:{efficiency:.3f}"
    elif efficiency <= 0.18 and slope_norm <= 0.45:
        structure_regime = "ranging"
        structure_score = min(1.0, 0.65 + (0.20 - efficiency))
        structure_reason = f"low_directional_efficiency:{efficiency:.3f}"
    else:
        structure_regime = "transitional"
        structure_score = 0.55
        structure_reason = f"mixed_efficiency:{efficiency:.3f}"

    recent_atr = mean(true_ranges[-14:])
    baseline_atr = mean(true_ranges[:-14]) if len(true_ranges) > 28 else mean(true_ranges)
    atr_ratio = recent_atr / baseline_atr if baseline_atr else 1.0
    last_body = abs(closes[-1] - opens[-1])
    last_range = ranges[-1] or 1.0
    last_wick_ratio = max(highs[-1] - max(closes[-1], opens[-1]), min(closes[-1], opens[-1]) - lows[-1]) / last_range

    if atr_ratio <= 0.75:
        volatility_regime = "compression"
        volatility_score = min(1.0, 0.65 + (0.75 - atr_ratio))
        volatility_reason = f"atr_compression_ratio:{atr_ratio:.3f}"
    elif atr_ratio >= 1.45 and last_wick_ratio >= 0.55:
        volatility_regime = "exhaustion"
        volatility_score = min(1.0, 0.60 + min(atr_ratio - 1.0, 1.0) * 0.35 + last_wick_ratio * 0.15)
        volatility_reason = f"expanded_atr_with_rejection_wick:{atr_ratio:.3f}"
    else:
        volatility_regime = "expansion"
        volatility_score = min(1.0, 0.55 + min(abs(atr_ratio - 1.0), 0.8) * 0.35)
        volatility_reason = f"atr_expansion_ratio:{atr_ratio:.3f}"

    high_sweeps, low_sweeps = _count_sweeps(usable, window=10)
    sweep_rate = (high_sweeps + low_sweeps) / max(len(usable) - 10, 1)
    if sweep_rate >= 0.18:
        liquidity_regime = "sweep-dominant"
        liquidity_score = min(1.0, 0.60 + sweep_rate * 1.4)
        liquidity_reason = f"sweep_rate:{sweep_rate:.3f}"
    else:
        first_half = closes[: len(closes) // 2]
        prior_move = mean(closes[-10:]) - mean(first_half[:10])
        if prior_move <= 0:
            liquidity_regime = "accumulation"
            liquidity_reason = "range_after_downward_or_flat_context"
        else:
            liquidity_regime = "distribution"
            liquidity_reason = "range_after_upward_context"
        liquidity_score = 0.58 if structure_regime == "trending" else 0.68

    sample_score = min(1.0, len(usable) / 80)
    confidence = _clamp(
        sample_score * 0.20
        + structure_score * 0.30
        + volatility_score * 0.25
        + liquidity_score * 0.25
    )
    return RegimeAssessment(
        structure_regime=structure_regime,
        volatility_regime=volatility_regime,
        liquidity_regime=liquidity_regime,
        confidence=round(confidence, 4),
        components={
            "sample": sample_score,
            "structure": structure_score,
            "volatility": volatility_score,
            "liquidity": liquidity_score,
            "directional_efficiency": efficiency,
            "atr_ratio": atr_ratio,
            "sweep_rate": sweep_rate,
        },
        reasons=[structure_reason, volatility_reason, liquidity_reason],
    )


def _true_ranges(candles: Sequence[Candle]) -> list[float]:
    ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high = _float(candle.high)
        low = _float(candle.low)
        close = _float(candle.close)
        if previous_close is None:
            ranges.append(max(high - low, 0.0))
        else:
            ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close), 0.0))
        previous_close = close
    return ranges


def _count_sweeps(candles: Sequence[Candle], *, window: int) -> tuple[int, int]:
    high_sweeps = 0
    low_sweeps = 0
    for index in range(window, len(candles)):
        previous = candles[index - window:index]
        candle = candles[index]
        prior_high = max(_float(c.high) for c in previous)
        prior_low = min(_float(c.low) for c in previous)
        close = _float(candle.close)
        if _float(candle.high) > prior_high and close < prior_high:
            high_sweeps += 1
        if _float(candle.low) < prior_low and close > prior_low:
            low_sweeps += 1
    return high_sweeps, low_sweeps


def _float(value: Decimal) -> float:
    return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
