from __future__ import annotations

import unittest

from tools.smc_webbridge_analyst import build_chart_url, normalize_tradingview_symbol


class WebBridgeCaptureConfigTests(unittest.TestCase):
    def test_btcusdt_defaults_to_binance_usdm_perp_for_source_alignment(self) -> None:
        tv_symbol, instrument, exchange = normalize_tradingview_symbol("BTCUSDT")

        self.assertEqual(tv_symbol, "BINANCE:BTCUSDT.P")
        self.assertEqual(instrument, "BTCUSDT")
        self.assertEqual(exchange, "BINANCE")

    def test_btcusd_defaults_to_bitstamp_for_source_alignment(self) -> None:
        tv_symbol, instrument, exchange = normalize_tradingview_symbol("BTCUSD")

        self.assertEqual(tv_symbol, "BITSTAMP:BTCUSD")
        self.assertEqual(instrument, "BTCUSD")
        self.assertEqual(exchange, "BITSTAMP")

    def test_prefixed_symbol_is_preserved(self) -> None:
        tv_symbol, instrument, exchange = normalize_tradingview_symbol("OANDA:EURUSD")

        self.assertEqual(tv_symbol, "OANDA:EURUSD")
        self.assertEqual(instrument, "EURUSD")
        self.assertEqual(exchange, "OANDA")

    def test_chart_url_encodes_exchange_symbol_and_interval(self) -> None:
        url = build_chart_url("BITSTAMP:BTCUSD", "4H")

        self.assertIn("symbol=BITSTAMP%3ABTCUSD", url)
        self.assertIn("interval=240", url)


if __name__ == "__main__":
    unittest.main()
