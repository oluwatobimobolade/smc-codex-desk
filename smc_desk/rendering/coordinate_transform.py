import pandas as pd
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Tuple, Sequence
from pydantic import BaseModel, PrivateAttr

class CoordinateTransform(BaseModel):
    chart_width_px: float
    chart_height_px: float
    plot_left_px: float
    plot_right_px: float
    plot_top_px: float
    plot_bottom_px: float
    visible_start_time: datetime
    visible_end_time: datetime
    visible_bar_count: int
    minimum_visible_price: Decimal
    maximum_visible_price: Decimal
    tick_size: Decimal
    scale_type: str = "linear"
    device_pixel_ratio: float = 1.0
    x_spacing_mode: str = "uniform"
    renderer_version: str = "2.0.0"

    _df: Any = PrivateAttr(default=None)
    _fig: Any = PrivateAttr(default=None)
    _ax: Any = PrivateAttr(default=None)

    def initialize_mapping(self, df: pd.DataFrame, fig: Any, ax: Any):
        self._df = df
        self._fig = fig
        self._ax = ax

    def _get_time_index(self, time: datetime) -> float:
        if self._df is None or len(self._df) == 0:
            return 0.0
        ts = pd.to_datetime(time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        
        # Exact match
        idx_match = self._df.index[self._df['timestamp'] == ts]
        if len(idx_match) > 0:
            return float(idx_match[0])
            
        # Interpolation/extrapolation
        timestamps = pd.to_datetime(self._df['timestamp']).values
        ts_val = ts.to_datetime64()
        
        if ts_val <= timestamps[0]:
            return 0.0
        if ts_val >= timestamps[-1]:
            return float(len(self._df) - 1)
            
        for i in range(len(timestamps) - 1):
            if timestamps[i] <= ts_val <= timestamps[i+1]:
                diff_total = (timestamps[i+1] - timestamps[i])
                diff_part = (ts_val - timestamps[i])
                ratio = diff_part / diff_total if diff_total else 0.0
                return float(i) + float(ratio)
        return 0.0

    def time_to_x(self, time: datetime) -> float:
        idx = self._get_time_index(time)
        return self.candle_index_to_x(idx)

    def candle_index_to_x(self, index: float) -> float:
        if self._ax is not None:
            # Use matplotlib transData to get exact display coordinate
            display_coords = self._ax.transData.transform((index, float(self.minimum_visible_price)))
            return float(display_coords[0])
        # Fallback linear mapping
        ratio = index / max(1.0, float(self.visible_bar_count - 1))
        return self.plot_left_px + ratio * (self.plot_right_px - self.plot_left_px)

    def price_to_y(self, price: Decimal) -> float:
        if self._ax is not None:
            display_coords = self._ax.transData.transform((0, float(price)))
            return float(self.chart_height_px - display_coords[1])
        # Fallback linear mapping
        diff_price = self.maximum_visible_price - self.minimum_visible_price
        if diff_price == 0:
            ratio = 0.5
        else:
            ratio = float((price - self.minimum_visible_price) / diff_price)
        return self.plot_bottom_px - ratio * (self.plot_bottom_px - self.plot_top_px)

    def x_to_time(self, x: float) -> datetime:
        if self._ax is not None and self._df is not None and len(self._df) > 0:
            data_coords = self._ax.transData.inverted().transform((x, 0))
            idx = int(round(max(0, min(len(self._df) - 1, data_coords[0]))))
            ts = self._df.iloc[idx]["timestamp"]
            return pd.to_datetime(ts).to_pydatetime().replace(tzinfo=timezone.utc)
            
        # Fallback
        ratio = (x - self.plot_left_px) / max(1.0, self.plot_right_px - self.plot_left_px)
        idx = int(round(ratio * (self.visible_bar_count - 1)))
        idx = max(0, min(self.visible_bar_count - 1, idx))
        if self._df is not None and len(self._df) > 0:
            ts = self._df.iloc[idx]["timestamp"]
            return pd.to_datetime(ts).to_pydatetime().replace(tzinfo=timezone.utc)
        return self.visible_start_time

    def y_to_price(self, y: float) -> Decimal:
        if self._ax is not None:
            display_y = self.chart_height_px - y
            data_coords = self._ax.transData.inverted().transform((0, display_y))
            raw_val = Decimal(f"{data_coords[1]:.8f}")
            ticks = round(raw_val / self.tick_size)
            return Decimal(str(ticks)) * self.tick_size
            
        # Fallback
        ratio = (self.plot_bottom_px - y) / max(1.0, self.plot_bottom_px - self.plot_top_px)
        price_val = self.minimum_visible_price + Decimal(str(ratio)) * (self.maximum_visible_price - self.minimum_visible_price)
        # Quantize to tick size
        if self.tick_size > 0:
            ticks = round(price_val / self.tick_size)
            price_val = Decimal(str(ticks)) * self.tick_size
        return price_val

    def bounding_box_for_price_zone(self, start_time: datetime, end_time: datetime, price_low: Decimal, price_high: Decimal) -> Tuple[float, float, float, float]:
        x1 = self.time_to_x(start_time)
        x2 = self.time_to_x(end_time)
        y1 = self.price_to_y(price_high) # Y is inverted, so price_high has smaller Y
        y2 = self.price_to_y(price_low)
        return (x1, x2, y1, y2)

    def bounding_box_for_candle_range(self, start_idx: int, end_idx: int, price_low: Decimal, price_high: Decimal) -> Tuple[float, float, float, float]:
        x1 = self.candle_index_to_x(float(start_idx))
        x2 = self.candle_index_to_x(float(end_idx))
        y1 = self.price_to_y(price_high)
        y2 = self.price_to_y(price_low)
        return (x1, x2, y1, y2)
