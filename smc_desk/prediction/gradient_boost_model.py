import pandas as pd
import numpy as np

try:
    import xgboost as xgb
except ImportError:
    pass

class GradientBoostModel:
    """
    Model B: Non-linear tabular model built ONLY to demonstrate
    incremental performance over Model A.
    """
    def __init__(self):
        # We use a multi-class objective to handle the 3 competing states
        # 0: unresolved, 1: target_first, 2: stop_first
        self.model = None
        self.is_trained = False
        
    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """
        Train XGBoost on the feature set.
        """
        try:
            self.model = xgb.XGBClassifier(
                objective='multi:softprob',
                num_class=3,
                eval_metric='mlogloss',
                use_label_encoder=False,
                max_depth=4, # Restrict depth to prevent aggressive curve fitting
                n_estimators=100,
                learning_rate=0.05
            )
            self.model.fit(X, y)
            self.is_trained = True
        except NameError:
            raise ImportError("XGBoost is not installed.")
            
    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.is_trained or self.model is None:
            raise ValueError("XGBoost model is not trained.")
            
        probs = self.model.predict_proba(X)
        return pd.DataFrame({
            "p_unresolved": probs[:, 0],
            "p_target_first": probs[:, 1],
            "p_stop_first": probs[:, 2]
        }, index=X.index)
