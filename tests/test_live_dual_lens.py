from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from tools.analyze_live_dual_lens import drop_unclosed_candles


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:15:00+00:00",
                    "2026-01-01T00:30:00+00:00",
                ]
            ),
            "open": [1.0, 2.0, 3.0],
            "high": [1.0, 2.0, 3.0],
            "low": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0],
            "volume": [10.0, 10.0, 10.0],
        }
    )


class LiveDualLensTests(unittest.TestCase):
    def test_drop_unclosed_candles_uses_close_time_not_boundary_timestamp(self) -> None:
        now = datetime(2026, 1, 1, 0, 37, tzinfo=timezone.utc)

        closed = drop_unclosed_candles(_df(), now=now, step_seconds=900)

        self.assertEqual(
            [ts.isoformat() for ts in closed["timestamp"]],
            ["2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00"],
        )

    def test_drop_unclosed_candles_keeps_boundary_candle_after_close(self) -> None:
        now = datetime(2026, 1, 1, 0, 45, tzinfo=timezone.utc)

        closed = drop_unclosed_candles(_df(), now=now, step_seconds=900)

        self.assertEqual(
            [ts.isoformat() for ts in closed["timestamp"]],
            [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:15:00+00:00",
                "2026-01-01T00:30:00+00:00",
            ],
        )


if __name__ == "__main__":
    unittest.main()
