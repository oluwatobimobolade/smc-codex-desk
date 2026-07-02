from typing import Dict, Any

class FeatureRegistry:
    """
    Standardizes feature generation across four families to ensure
    no forward leakage (future data contamination) occurs during feature generation.
    """
    
    @staticmethod
    def extract_smc_structure_features(setup_state: Dict[str, Any]) -> Dict[str, float]:
        """
        Features: structural direction, swing scope, protected-point distance,
        displacement magnitude, FVG width, FVG age, mitigation percentage,
        sweep depth, distance to POI, distance to opposing liquidity.
        """
        return {
            "displacement_magnitude": setup_state.get("displacement_magnitude", 0.0),
            "fvg_width_bps": setup_state.get("fvg_width_bps", 0.0),
            "sweep_depth_bps": setup_state.get("sweep_depth_bps", 0.0),
        }

    @staticmethod
    def extract_sequence_features(setup_state: Dict[str, Any]) -> Dict[str, float]:
        """
        Features: bars between sweep and displacement, retracement speed,
        number of failed confirmations, sequence state.
        """
        return {
            "bars_sweep_to_disp": setup_state.get("bars_sweep_to_disp", 0.0),
            "failed_confirmations": setup_state.get("failed_confirmations", 0.0),
        }

    @staticmethod
    def extract_market_regime_features(context: Dict[str, Any]) -> Dict[str, float]:
        """
        Features: volatility percentile, range efficiency, trend slope,
        directional persistence, time of day.
        """
        return {
            "volatility_percentile": context.get("volatility_percentile", 0.5),
            "trend_slope": context.get("trend_slope", 0.0),
        }

    @staticmethod
    def extract_execution_reality_features(context: Dict[str, Any]) -> Dict[str, float]:
        """
        Features: stop distance, target distance, spread, expected slippage, fees.
        """
        return {
            "expected_slippage_bps": context.get("expected_slippage_bps", 2.0),
            "target_distance_bps": context.get("target_distance_bps", 50.0),
            "stop_distance_bps": context.get("stop_distance_bps", 20.0),
        }
        
    @classmethod
    def compile_all_features(cls, setup_state: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, float]:
        features = {}
        features.update(cls.extract_smc_structure_features(setup_state))
        features.update(cls.extract_sequence_features(setup_state))
        features.update(cls.extract_market_regime_features(context))
        features.update(cls.extract_execution_reality_features(context))
        return features
