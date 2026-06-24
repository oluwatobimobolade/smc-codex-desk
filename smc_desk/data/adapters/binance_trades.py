import os
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
import threading

import requests

from smc_desk.data.schemas import RawTrade

class BinanceTradeAdapter:
    def __init__(self, symbol: str, is_futures: bool = True):
        self.symbol = symbol
        self.is_futures = is_futures
        self.base_url = "https://fapi.binance.com" if is_futures else "https://api.binance.com"
        self._running = False
        self._thread = None
        self._callbacks = []
    
    def register_callback(self, callback):
        self._callbacks.append(callback)
        
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
            
    def _poll_loop(self):
        last_id = None
        while self._running:
            try:
                trades = self._fetch_recent_agg_trades(limit=1000)
                for t in trades:
                    if last_id and t['a'] <= last_id:
                        continue
                        
                    raw_trade = RawTrade(
                        venue="binance",
                        instrument=f"{self.symbol}_PERP" if self.is_futures else self.symbol,
                        market_type="perpetual" if self.is_futures else "spot",
                        symbol=self.symbol,
                        base_asset=self.symbol.replace("USDT", ""),
                        quote_asset="USDT",
                        event_time=datetime.fromtimestamp(t['T'] / 1000, tz=timezone.utc),
                        receive_time=datetime.utcnow().replace(tzinfo=timezone.utc),
                        sequence_id=t['a'],
                        price=Decimal(str(t['p'])),
                        quantity=Decimal(str(t['q'])),
                        trade_side="seller_maker" if t['m'] else "buyer_maker",
                        data_source="rest_polling",
                        connection_id="binance_rest_01"
                    )
                    
                    last_id = t['a']
                    for cb in self._callbacks:
                        cb(raw_trade)
                        
            except Exception as e:
                print(f"Error fetching trades: {e}")
                
            time.sleep(1.0)
            
    def _fetch_recent_agg_trades(self, limit=1000):
        url = f"{self.base_url}/fapi/v1/aggTrades" if self.is_futures else f"{self.base_url}/api/v3/aggTrades"
        params = {"symbol": self.symbol, "limit": limit}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
