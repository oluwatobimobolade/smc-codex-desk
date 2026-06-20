from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from unittest.mock import patch

import pandas as pd

from tools import backtest_smc_elite, backtest_smc_elite_mtf
from tools.backtest_smc_elite import simulate_trade
from tools.derive_htf_from_15m import derive_htf
from tools.download_binance_futures_ohlcv import (
    archive_files as binance_archive_files,
    parse_datetime as parse_binance_datetime,
    parse_kline_csv_bytes,
    parse_rest_klines,
)
from tools.download_bitstamp_ohlcv import download_ohlcv, fetch_ohlc_page, parse_ohlc_rows
from tools.run_mtf_research_grid import EXPERIMENTS, ExperimentSpec


class BacktestToolTests(unittest.TestCase):
    def test_binance_archive_uses_monthly_history_and_daily_final_month(self) -> None:
        files = binance_archive_files(
            "BTCUSDT",
            "15m",
            parse_binance_datetime("2026-05-20"),
            parse_binance_datetime("2026-06-20"),
        )

        labels = [archive.label for archive in files]
        self.assertEqual(labels[0], "BTCUSDT-15m-2026-05")
        self.assertEqual(labels[1], "BTCUSDT-15m-2026-06-01")
        self.assertEqual(labels[-1], "BTCUSDT-15m-2026-06-19")
        self.assertEqual(len([label for label in labels if "2026-06-" in label]), 19)

    def test_parse_binance_archive_rows_keeps_engine_columns_and_provenance(self) -> None:
        payload = b"""open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
1767225600000,100.0,102.0,99.0,101.0,12.5,1767226499999,1262.5,42,6.0,606.0,0
"""

        rows = parse_kline_csv_bytes(
            payload,
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 2, tzinfo=timezone.utc),
            source="unit",
        )

        self.assertEqual(rows[0]["timestamp"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(rows[0]["open"], 100.0)
        self.assertEqual(rows[0]["quote_volume"], 1262.5)
        self.assertEqual(rows[0]["trade_count"], 42)
        self.assertEqual(rows[0]["source"], "unit")

    def test_parse_binance_rest_rows_accepts_microsecond_archive_precision(self) -> None:
        rows = parse_rest_klines(
            [
                [
                    1767225600000000,
                    "100.0",
                    "102.0",
                    "99.0",
                    "101.0",
                    "12.5",
                    1767226499999000,
                    "1262.5",
                    42,
                    "6.0",
                    "606.0",
                    "0",
                ]
            ],
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 2, tzinfo=timezone.utc),
            source="rest-unit",
        )

        self.assertEqual(rows[0]["timestamp"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(rows[0]["close_time"], "2026-01-01T00:14:59.999000+00:00")

    def test_derive_htf_from_15m_drops_incomplete_buckets(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT_15m_4year.csv"
            timestamps = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
            pd.DataFrame(
                {
                    "timestamp": [ts.isoformat() for ts in timestamps],
                    "open": list(range(100)),
                    "high": [value + 1 for value in range(100)],
                    "low": [value - 1 for value in range(100)],
                    "close": [value + 0.5 for value in range(100)],
                    "volume": [10.0] * 100,
                    "close_time": [(ts + pd.Timedelta(minutes=15) - pd.Timedelta(milliseconds=1)).isoformat() for ts in timestamps],
                    "quote_volume": [100.0] * 100,
                    "trade_count": [3] * 100,
                    "taker_buy_base_volume": [4.0] * 100,
                    "taker_buy_quote_volume": [40.0] * 100,
                }
            ).to_csv(path, index=False)

            one_hour = derive_htf(path, "1h")
            one_day = derive_htf(path, "1d")

        self.assertEqual(len(one_hour), 25)
        self.assertEqual(len(one_day), 1)
        self.assertEqual(one_day.iloc[0]["volume"], 960.0)
        self.assertEqual(one_day.iloc[0]["quote_volume"], 9600.0)
        self.assertEqual(one_day.iloc[0]["trade_count"], 288)
        self.assertEqual(one_day.iloc[0]["taker_buy_base_volume"], 384.0)
        self.assertEqual(one_day.iloc[0]["taker_buy_quote_volume"], 3840.0)
        self.assertEqual(one_day.iloc[0]["close_time"], "2026-01-01T23:59:59.999000+00:00")
        self.assertEqual(one_day.iloc[0]["source"], "derived_from_15m:BTCUSDT_15m_4year.csv")

    def test_bitstamp_fetch_falls_back_after_dns_failure(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"data": {"ohlc": []}}'

        with patch("tools.download_bitstamp_ohlcv.urlopen", side_effect=[URLError("dns"), FakeResponse()]):
            payload = fetch_ohlc_page("solusd", 900, 1718755200, 1718841600, retries=0)

        self.assertEqual(payload, {"data": {"ohlc": []}})

    def test_bitstamp_fetch_uses_pinned_ip_after_host_failures(self) -> None:
        expected = {"data": {"pair": "SOL/USD", "ohlc": []}}
        with (
            patch("tools.download_bitstamp_ohlcv.urlopen", side_effect=URLError("dns")),
            patch("tools.download_bitstamp_ohlcv._fetch_pinned_json", return_value=expected) as pinned_fetch,
        ):
            payload = fetch_ohlc_page("solusd", 900, 1718755200, 1718841600, retries=0)

        self.assertEqual(payload, expected)
        pinned_fetch.assert_called_once()

    def test_parse_bitstamp_ohlc_rows_sorts_out_numeric_fields(self) -> None:
        payload = {
            "data": {
                "ohlc": [
                    {
                        "timestamp": "1767225600",
                        "open": "100.10",
                        "high": "101.20",
                        "low": "99.80",
                        "close": "100.70",
                        "volume": "12.5",
                    }
                ]
            }
        }

        rows = parse_ohlc_rows(payload)

        self.assertEqual(rows[0]["timestamp"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(rows[0]["open"], 100.10)
        self.assertEqual(rows[0]["volume"], 12.5)

    def test_download_filters_rows_to_requested_page_window(self) -> None:
        payload = {
            "data": {
                "ohlc": [
                    {"timestamp": "1767224700", "open": "99", "high": "100", "low": "98", "close": "99", "volume": "1"},
                    {"timestamp": "1767225600", "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1"},
                    {"timestamp": "1767312000", "open": "101", "high": "102", "low": "100", "close": "101", "volume": "1"},
                    {"timestamp": "1767312900", "open": "102", "high": "103", "low": "101", "close": "102", "volume": "1"},
                ]
            }
        }

        with patch("tools.download_bitstamp_ohlcv.fetch_ohlc_page", return_value=payload):
            rows = download_ohlcv(
                market="btcusd",
                step=900,
                start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 2, tzinfo=timezone.utc),
                sleep_seconds=0,
            )

        self.assertEqual([row["timestamp"] for row in rows], ["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"])

    def test_simulator_does_not_count_signal_candle_target_hit(self) -> None:
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=6, freq="15min"),
                "open": [100, 100, 100, 100, 100, 100],
                "high": [101, 101, 106, 101, 101, 105],
                "low": [99, 99, 99, 99, 99, 99],
                "close": [100, 100, 100, 100, 100, 104],
                "volume": [1000] * 6,
            }
        )

        simulation, _ = simulate_trade(
            df=df,
            signal_index=2,
            direction="bullish",
            entry_low=99.5,
            entry_high=100.0,
            invalidation=98.0,
            target=105.0,
            entry_wait_bars=2,
            max_hold_bars=3,
            cost_bps=0.0,
            entry_mode="boundary",
        )

        self.assertEqual(simulation["entry_index"], 3)
        self.assertNotEqual(simulation["exit_index"], 2)

    def test_single_timeframe_backtest_defaults_to_confirmed_setups_only(self) -> None:
        argv = [
            "backtest_smc_elite.py",
            "--ohlcv",
            "dummy.csv",
            "--symbol",
            "BTCUSD",
            "--timeframe",
            "15m",
        ]

        with patch("sys.argv", argv):
            args = backtest_smc_elite.parse_args()

        self.assertEqual(args.watch_entry, "off")

    def test_mtf_backtest_defaults_to_confirmed_setups_only(self) -> None:
        argv = [
            "backtest_smc_elite_mtf.py",
            "--ohlcv",
            "dummy.csv",
            "--symbol",
            "BTCUSD",
            "--run-name",
            "unit",
        ]

        with patch("sys.argv", argv):
            args = backtest_smc_elite_mtf.parse_args()

        self.assertEqual(args.include_watch_retrace, "off")

    def test_research_grid_keeps_watch_retrace_as_explicit_diagnostic(self) -> None:
        self.assertEqual(ExperimentSpec("unit", "baseline").include_watch_retrace, "off")
        diagnostics = [experiment for experiment in EXPERIMENTS if experiment.include_watch_retrace == "on"]

        self.assertEqual([experiment.experiment_id for experiment in diagnostics], ["watch_retrace_diagnostic"])


if __name__ == "__main__":
    unittest.main()
