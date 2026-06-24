from typing import List
from datetime import datetime

from smc_desk.data.schemas import Candle

def replay_candles(candles: List[Candle], decision_time: datetime) -> List[Candle]:
    """
    Deterministic replay up to decision_time, rejecting unclosed candles.
    Only returns candles that have fully closed before or exactly at decision_time.
    """
    valid_candles = []
    for candle in candles:
        if candle.close_time <= decision_time and candle.is_closed:
            valid_candles.append(candle)
        else:
            # Since the list is expected to be sorted by time, we can break early
            break
            
    return valid_candles
