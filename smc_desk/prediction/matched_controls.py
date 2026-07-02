import pandas as pd
import numpy as np
from typing import Dict, Any

class MatchedControlGenerator:
    """
    Generates matched control samples to test whether SMC contributes
    predictive value beyond baseline market conditions.
    """
    
    def __init__(self, market_data: pd.DataFrame):
        """
        market_data: full OHLCV history with pre-calculated regime features
                     (volatility, trend, session).
        """
        self.market_data = market_data
        
    def generate_control_for_setup(self, setup_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Given a valid SMC setup's features, find a random historical timestamp
        that is NOT an SMC setup, but matches the context:
        - Volatility
        - Trend slope
        - Session / time of day
        - Stop / target distances
        """
        if self.market_data.empty:
            raise ValueError("Cannot generate matched control from empty market_data.")

        required_outcomes = {"target_first", "stop_first", "unresolved"}
        missing_outcomes = required_outcomes.difference(self.market_data.columns)
        if missing_outcomes:
            raise ValueError(f"market_data missing control outcome columns: {sorted(missing_outcomes)}")

        candidates = self.market_data.copy()
        if "is_smc_setup" in candidates.columns:
            candidates = candidates[candidates["is_smc_setup"] == False]  # noqa: E712
        if "setup_id" in setup_features and "setup_id" in candidates.columns:
            candidates = candidates[candidates["setup_id"] != setup_features["setup_id"]]
        if candidates.empty:
            raise ValueError("No non-SMC control candidates available after exclusions.")

        distance = pd.Series(0.0, index=candidates.index)
        numeric_features = [
            "volatility_percentile",
            "trend_slope",
            "stop_distance_atr",
            "target_distance_atr",
            "atr_percentile",
        ]
        used_features = 0
        for feature in numeric_features:
            if feature not in setup_features or feature not in candidates.columns:
                continue
            series = pd.to_numeric(candidates[feature], errors="coerce")
            scale = max(float(series.std(skipna=True) or 0.0), 1e-9)
            distance += ((series - float(setup_features[feature])) / scale).fillna(10.0).abs()
            used_features += 1

        if "session" in setup_features and "session" in candidates.columns:
            distance += np.where(candidates["session"] == setup_features["session"], 0.0, 1.0)
            used_features += 1

        if used_features == 0:
            raise ValueError("No shared matching features between setup_features and market_data.")

        best_idx = distance.sort_values(kind="mergesort").index[0]
        control_features = candidates.loc[best_idx].to_dict()
        control_features["is_smc_setup"] = False
        control_features["matched_control_index"] = best_idx
        control_features["match_distance"] = float(distance.loc[best_idx])

        outcomes = [bool(control_features["target_first"]), bool(control_features["stop_first"]), bool(control_features["unresolved"])]
        if sum(outcomes) != 1:
            raise ValueError(f"Matched control row {best_idx} has invalid mutually exclusive outcomes.")

        return control_features
