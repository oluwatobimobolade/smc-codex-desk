"""Price-provenance tests for the Fusion Engine.

Every price referenced by the fusion output must trace to a price computed by
the deterministic engine. Fusion may select among engine-owned levels; it may
not invent new ones.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smc_desk.engine import analyze_dataframe
from smc_desk.fusion_engine import FusionEngine
from smc_desk.intent_detector import IntentDetector, MarketContext
from smc_desk.rules import RuleConfig
from smc_desk.sequence_memory import BarSnapshot, SequenceMemory


def _make_df() -> pd.DataFrame:
    rows = []
    price = 100.0
    for i in range(80):
        hour, minute = i // 60, i % 60
        open_p = price
        close = price + (-1 if i % 2 else 1) * 0.3
        high = max(open_p, close) + 0.2
        low = min(open_p, close) - 0.2
        rows.append({
            "timestamp": f"2026-01-01T{hour:02d}:{minute:02d}:00",
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
        })
        price = close
    return pd.DataFrame(rows)


def _engine_price_set(engine_result) -> set[str]:
    """Collect every price produced by the engine across both directions."""
    prices: set[str] = set()
    for plan in (engine_result.bullish_plan, engine_result.bearish_plan, engine_result.trade_plan):
        if plan is None:
            continue
        for price in (
            plan.entry_low,
            plan.entry_high,
            plan.invalidation,
            plan.liquidity_target,
            plan.structural_invalidation,
            plan.execution_invalidation,
        ):
            if price is not None:
                prices.add(f"{price:.5f}")
        for target in plan.targets:
            prices.add(f"{target:.5f}")
    return prices


class FusionPriceProvenanceTests(unittest.TestCase):
    """Fusion output prices must come from the engine."""

    def setUp(self) -> None:
        self.df = _make_df()
        config = RuleConfig()
        self.engine_result, _ = analyze_dataframe(self.df, "TEST", "15m", config)

        mem = SequenceMemory()
        for idx, row in self.df.iterrows():
            mem.process_bar(
                BarSnapshot(
                    index=idx,
                    timestamp=str(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        self.memory = mem

        detector = IntentDetector()
        self.intent_result = detector.detect_intent(
            sequence_memory=mem,
            context=MarketContext(symbol="TEST", timeframe="15m"),
        )

    def test_all_fusion_prices_trace_to_engine(self) -> None:
        fusion = FusionEngine()
        result = fusion.fuse(
            engine_result=self.engine_result,
            sequence_memory=self.memory,
            intent_result=self.intent_result,
        )
        engine_prices = _engine_price_set(self.engine_result)
        for price_str, source in result.price_sources.items():
            normalized = f"{float(price_str):.5f}"
            self.assertIn(
                normalized,
                engine_prices,
                f"Fusion references price {price_str} from {source}, but it is not in engine prices.",
            )

    def test_fusion_does_not_invent_prices(self) -> None:
        """FusionResult contains no price fields outside price_sources and summaries."""
        fusion = FusionEngine()
        result = fusion.fuse(
            engine_result=self.engine_result,
            sequence_memory=self.memory,
            intent_result=self.intent_result,
        )
        # Any numeric-looking string in the output that is not in price_sources
        # would be an invented price.
        payload = result.to_dict()
        allowed_invented = {"fused_confidence", "engine_primary_confidence", "contested"}

        def scan(obj, path: str = "root") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in allowed_invented:
                        continue
                    scan(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for idx, value in enumerate(obj):
                    scan(value, f"{path}[{idx}]")
            elif isinstance(obj, str):
                # Skip non-numeric and obvious non-price strings.
                if obj in {"bullish", "bearish", "neutral", "Pass", "Watch", "Execute", "", "N/A"}:
                    return
                try:
                    float(obj)
                except ValueError:
                    return
                # If it looks like a price, it must be in price_sources.
                if "." in obj and len(obj.split(".")[-1]) >= 4:
                    self.assertIn(
                        obj,
                        result.price_sources,
                        f"Possible invented price {obj!r} at {path}",
                    )

        scan(payload)


if __name__ == "__main__":
    unittest.main()
