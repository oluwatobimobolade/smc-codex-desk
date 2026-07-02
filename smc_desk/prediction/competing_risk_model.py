import pandas as pd
import numpy as np
from typing import Dict

class CompetingRiskDiscreteHazardModel:
    """
    Implements a discrete-time hazard model for competing risks
    (target reached first vs. stop reached first) over a maximum bar horizon.
    """
    def __init__(self, max_horizon_bars: int = 32, hazard_model=None):
        self.max_horizon_bars = max_horizon_bars
        if hazard_model is None:
            try:
                from sklearn.linear_model import LogisticRegression
            except ImportError as exc:
                raise ImportError("scikit-learn is required unless a hazard_model is injected.") from exc
            hazard_model = LogisticRegression(multi_class='multinomial', solver='lbfgs', max_iter=1000)
        self.hazard_model = hazard_model
        self.feature_columns: list[str] = []
        self.is_trained = False
        
    def fit(self, person_period_df: pd.DataFrame, y_event: pd.Series) -> None:
        """
        Expects a dataset expanded such that each row represents one bar for one setup,
        until the setup resolves or the horizon is reached.
        y_event = 0 (no event), 1 (target), 2 (stop)
        """
        if person_period_df.empty:
            raise ValueError("Cannot fit hazard model on an empty dataset.")
        observed_classes = set(y_event.astype(int).unique())
        if not observed_classes.issubset({0, 1, 2}) or not {0, 1, 2}.issubset(observed_classes):
            raise ValueError("y_event must contain the competing-risk classes 0=no event, 1=target, 2=stop.")
        self.feature_columns = list(person_period_df.columns)
        self.hazard_model.fit(person_period_df, y_event)
        self.is_trained = True
        
    def predict_cumulative_incidence(self, X_base: pd.DataFrame) -> pd.DataFrame:
        """
        Predict the probability of target_first and stop_first before max horizon.
        For demonstration, assuming X_base provides feature sets to unroll.
        """
        if not self.is_trained:
            raise ValueError("Hazard model is not trained.")
            
        if X_base.empty:
            return pd.DataFrame(columns=["p_target_first", "p_stop_first", "p_unresolved"], index=X_base.index)

        target_probs = []
        stop_probs = []
        unresolved_probs = []
        class_to_idx = {int(label): idx for idx, label in enumerate(self.hazard_model.classes_)}

        for row_idx, row in X_base.iterrows():
            survival = 1.0
            cumulative_target = 0.0
            cumulative_stop = 0.0

            for step in range(1, self.max_horizon_bars + 1):
                feature_row = {}
                for column in self.feature_columns:
                    if column in X_base.columns:
                        feature_row[column] = row[column]
                    elif column in {"bar_index", "horizon_step", "time_step", "t"}:
                        feature_row[column] = step
                    else:
                        feature_row[column] = 0.0

                hazard_input = pd.DataFrame([feature_row], columns=self.feature_columns)
                probs = self.hazard_model.predict_proba(hazard_input)[0]
                h_none = float(probs[class_to_idx.get(0, -1)]) if 0 in class_to_idx else 0.0
                h_target = float(probs[class_to_idx.get(1, -1)]) if 1 in class_to_idx else 0.0
                h_stop = float(probs[class_to_idx.get(2, -1)]) if 2 in class_to_idx else 0.0

                cumulative_target += survival * h_target
                cumulative_stop += survival * h_stop
                survival *= max(0.0, min(1.0, h_none))

            total = cumulative_target + cumulative_stop + survival
            if total > 0:
                cumulative_target /= total
                cumulative_stop /= total
                survival /= total

            target_probs.append(cumulative_target)
            stop_probs.append(cumulative_stop)
            unresolved_probs.append(survival)

        return pd.DataFrame({
            "p_target_first": np.asarray(target_probs),
            "p_stop_first": np.asarray(stop_probs),
            "p_unresolved": np.asarray(unresolved_probs),
        }, index=X_base.index)
