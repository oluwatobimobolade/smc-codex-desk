import pandas as pd
from pathlib import Path
from typing import List, Protocol
from decimal import Decimal
from datetime import timedelta

from smc_desk.data.schemas import Candle, Instrument
from smc_desk.data.candle_builder import build_candles_from_ohlcv

class ExchangeAdapter(Protocol):
    venue: str
    def load_ohlcv(self, path: Path) -> List[Candle]: ...
    def instrument_info(self, symbol: str) -> Instrument: ...


class BinanceAdapter:
    venue = "binance"
    
    def load_ohlcv(self, path: Path, instrument: str, timeframe: str) -> List[Candle]:
        """Loads OHLCV from a Binance historical CSV file."""
        df = pd.read_csv(path)
        
        # Binance CSVs typically don't have column headers if downloaded raw, or have specific ones.
        # Assuming we normalise them or they are already: 
        # open_time, open, high, low, close, volume, close_time, quote_asset_volume, number_of_trades, taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore
        if len(df.columns) == 12 and 'open_time' not in df.columns:
            df.columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                'quote_asset_volume', 'trade_count', 'taker_buy_base', 'taker_buy_quote', 'ignore'
            ]
            
        # Ensure datetimes
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms', utc=True)
        
        return build_candles_from_ohlcv(df, self.venue, instrument, timeframe)

    def instrument_info(self, symbol: str) -> Instrument:
        # Mocking instrument info, in reality this would be fetched from the Binance API
        if symbol == "BTCUSDT":
            return Instrument(
                venue=self.venue,
                symbol=symbol,
                market_type="perpetual",
                base_asset="BTC",
                quote_asset="USDT",
                tick_size=Decimal("0.10"),
                lot_size=Decimal("0.001")
            )
        raise ValueError(f"Unknown symbol {symbol}")
