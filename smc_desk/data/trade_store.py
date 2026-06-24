import os
import csv
from datetime import datetime
from typing import List

from smc_desk.data.schemas import RawTrade

class TradeStore:
    def __init__(self, base_dir: str = "data/raw_trades"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._cache = {}  # To track sequence IDs to prevent duplicates if needed
        
    def _get_file_path(self, symbol: str, dt: datetime) -> str:
        date_str = dt.strftime("%Y%m%d")
        dir_path = os.path.join(self.base_dir, symbol, dt.strftime("%Y"), dt.strftime("%m"))
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{symbol}_trades_{date_str}.csv")
        
    def append_trade(self, trade: RawTrade):
        file_path = self._get_file_path(trade.symbol, trade.event_time)
        file_exists = os.path.exists(file_path)
        
        with open(file_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "venue", "instrument", "market_type", "symbol",
                    "base_asset", "quote_asset", "event_time", "receive_time",
                    "sequence_id", "price", "quantity", "trade_side",
                    "data_source", "connection_id"
                ])
                
            writer.writerow([
                trade.venue, trade.instrument, trade.market_type, trade.symbol,
                trade.base_asset, trade.quote_asset, trade.event_time.isoformat(),
                trade.receive_time.isoformat(), trade.sequence_id,
                str(trade.price), str(trade.quantity), trade.trade_side,
                trade.data_source, trade.connection_id
            ])
