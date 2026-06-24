import pandas as pd
from typing import Tuple

class CounterfactualGenerator:
    def __init__(self):
        pass

    def create_body_close_break_counterfactual(
        self,
        df: pd.DataFrame,
        level: float,
        break_candle_idx: int,
        tick_size: float = 0.05
    ) -> Tuple[pd.DataFrame, bool]:
        """
        Alters the close of the break candle to be exactly 1 tick ABOVE the level,
        converting a wick-only break candidate into a confirmed body-close break.
        Returns the modified DataFrame and a boolean indicating if it represents a confirmed break.
        """
        df_mod = df.copy()
        
        # Modify the close to be level + 1 tick
        df_mod.at[break_candle_idx, "close"] = level + tick_size
        df_mod.at[break_candle_idx, "high"] = max(df_mod.at[break_candle_idx, "high"], level + tick_size)
        
        return df_mod, True

    def create_wick_probe_counterfactual(
        self,
        df: pd.DataFrame,
        level: float,
        break_candle_idx: int,
        tick_size: float = 0.05
    ) -> Tuple[pd.DataFrame, bool]:
        """
        Alters the close of the break candle to be exactly 1 tick BELOW the level,
        while maintaining high above the level, representing a wick-only probe.
        """
        df_mod = df.copy()
        
        # Close is level - 1 tick, High is level + 2 ticks
        df_mod.at[break_candle_idx, "close"] = level - tick_size
        df_mod.at[break_candle_idx, "high"] = level + 2 * tick_size
        
        return df_mod, False
