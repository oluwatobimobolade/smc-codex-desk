import pandas as pd
from typing import Dict, Any, List
from decimal import Decimal

class GroundTruthAnnotator:
    def __init__(self):
        pass

    def compute_objective_ground_truth(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Computes mathematically determined ground truth annotations.
        E.g., exact FVG boundaries, exact wick crossings, exact body close breaks.
        """
        annotations = {
            "fvgs": [],
            "wick_breaks": [],
            "body_close_breaks": []
        }
        
        # Scan for exact FVG boundaries
        for i in range(2, len(df)):
            c1_hi = df.iloc[i-2]["high"]
            c3_lo = df.iloc[i]["low"]
            if c1_hi < c3_lo:
                annotations["fvgs"].append({
                    "candle_indices": (i-2, i-1, i),
                    "direction": "bullish",
                    "price_low": float(c1_hi),
                    "price_high": float(c3_lo)
                })
            
            c1_lo = df.iloc[i-2]["low"]
            c3_hi = df.iloc[i]["high"]
            if c1_lo > c3_hi:
                annotations["fvgs"].append({
                    "candle_indices": (i-2, i-1, i),
                    "direction": "bearish",
                    "price_low": float(c3_hi),
                    "price_high": float(c1_lo)
                })
                
        return annotations
