import numpy as np
import pandas as pd

try:
    from sklearn.calibration import IsotonicRegression
    from sklearn.metrics import brier_score_loss
except ImportError:
    pass

class ProbabilityCalibrator:
    """
    Implements sequential/rolling calibration methods to align raw model 
    outputs with true observed frequencies, and tracks Brier scores.
    """
    def __init__(self):
        self.calibrators = {
            "target": IsotonicRegression(out_of_bounds='clip'),
            "stop": IsotonicRegression(out_of_bounds='clip')
        }
        self.is_calibrated = False
        
    def fit_calibration(self, raw_probs: pd.DataFrame, true_outcomes: pd.DataFrame) -> None:
        """
        raw_probs: p_target_first, p_stop_first
        true_outcomes: boolean columns target_first, stop_first
        """
        self.calibrators["target"].fit(raw_probs["p_target_first"], true_outcomes["target_first"])
        self.calibrators["stop"].fit(raw_probs["p_stop_first"], true_outcomes["stop_first"])
        self.is_calibrated = True
        
    def calibrate(self, raw_probs: pd.DataFrame) -> pd.DataFrame:
        if not self.is_calibrated:
            raise ValueError("Calibrator is not fitted.")
            
        cal_target = self.calibrators["target"].predict(raw_probs["p_target_first"])
        cal_stop = self.calibrators["stop"].predict(raw_probs["p_stop_first"])
        
        # Enforce mutual exclusivity constraints after independent calibration
        total = cal_target + cal_stop
        cal_target = np.where(total > 1.0, cal_target / total, cal_target)
        cal_stop = np.where(total > 1.0, cal_stop / total, cal_stop)
        cal_unresolved = np.clip(1.0 - (cal_target + cal_stop), 0.0, 1.0)
        
        return pd.DataFrame({
            "p_target_first": cal_target,
            "p_stop_first": cal_stop,
            "p_unresolved": cal_unresolved
        }, index=raw_probs.index)

    @staticmethod
    def calculate_brier_score(calibrated_probs: pd.Series, true_outcomes: pd.Series) -> float:
        """
        Brier score measures both calibration and resolution.
        Lower is better (0 is perfect, 0.25 is random guessing for 50/50 prior).
        """
        return brier_score_loss(true_outcomes, calibrated_probs)
