from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

from smc_desk.data.schemas import RawTrade, Candle

class TradeCandleBuilder:
    def __init__(self, timeframe_minutes: int = 1):
        self.timeframe_minutes = timeframe_minutes
        self.current_candle: Optional[Candle] = None
        
    def _get_interval_start(self, dt: datetime) -> datetime:
        """Align datetime to the timeframe interval"""
        minutes = (dt.minute // self.timeframe_minutes) * self.timeframe_minutes
        return dt.replace(minute=minutes, second=0, microsecond=0)
        
    def process_trade(self, trade: RawTrade) -> Optional[Candle]:
        """Process a raw trade and return a closed candle if a boundary was crossed."""
        trade_interval_start = self._get_interval_start(trade.event_time)
        
        # If this is the first trade, initialize candle
        if self.current_candle is None:
            self._init_candle(trade, trade_interval_start)
            return None
            
        # If trade belongs to the current candle
        if trade_interval_start == self.current_candle.open_time:
            self._update_candle(trade)
            return None
            
        # If trade belongs to a future candle, close current and yield
        closed_candle = self.current_candle
        closed_candle.is_closed = True
        closed_candle.is_complete = True
        
        # Initialize new candle
        self._init_candle(trade, trade_interval_start)
        return closed_candle
        
    def _init_candle(self, trade: RawTrade, interval_start: datetime):
        interval_end = interval_start + timedelta(minutes=self.timeframe_minutes)
        self.current_candle = Candle(
            venue=trade.venue,
            instrument=trade.instrument,
            timeframe=f"{self.timeframe_minutes}m",
            open_time=interval_start,
            close_time=interval_end,
            open=trade.price,
            high=trade.price,
            low=trade.price,
            close=trade.price,
            volume=trade.quantity,
            trade_count=1,
            is_closed=False,
            is_complete=False,
            contains_gap=False,
            source_event_start=trade.event_time,
            source_event_end=trade.event_time
        )
        
    def _update_candle(self, trade: RawTrade):
        if trade.price > self.current_candle.high:
            self.current_candle.high = trade.price
        if trade.price < self.current_candle.low:
            self.current_candle.low = trade.price
            
        self.current_candle.close = trade.price
        self.current_candle.volume += trade.quantity
        self.current_candle.trade_count += 1
        self.current_candle.source_event_end = trade.event_time
