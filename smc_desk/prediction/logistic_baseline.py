import pandas as pd
import numpy as np

try:
    from sklearn.linear_model import LogisticRegression
except ImportError:
    pass # Will be handled by the environment

class LogisticBaselineModel:
    """
    Model A: Transparent statistical baseline using regularized logistic regression.
    Establishes clear interpretability and directional signs.
    """
    def __init__(self):
        self.model_target = LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000)
        self.model_stop = LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000)
        self.is_trained = False
        
    def fit(self, X: pd.DataFrame, y_target: pd.Series, y_stop: pd.Series) -> None:
        """
        Train the separate logistic models for the mutually exclusive outcomes.
        """
        self.model_target.fit(X, y_target)
        self.model_stop.fit(X, y_stop)
        self.is_trained = True
        
    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Predict the raw probabilities.
        Note: These are raw outputs. True competing risk calibration happens later.
        """
        if not self.is_trained:
            raise ValueError("Baseline model is not trained yet.")
            
        p_target = self.model_target.predict_proba(X)[:, 1]
        p_stop = self.model_stop.predict_proba(X)[:, 1]
        
        # Simple normalization for the mutually exclusive outcomes + unresolved
        total = p_target + p_stop
        # If total exceeds 1, normalize down. Unresolved is 1 - total
        p_target_norm = np.where(total > 1.0, p_target / total, p_target)
        p_stop_norm = np.where(total > 1.0, p_stop / total, p_stop)
        p_unresolved = np.clip(1.0 - (p_target_norm + p_stop_norm), 0.0, 1.0)
        
        return pd.DataFrame({
            "p_target_first": p_target_norm,
            "p_stop_first": p_stop_norm,
            "p_unresolved": p_unresolved
        }, index=X.index)

    def get_feature_importances(self, feature_names: list) -> dict:
        """
        Extract the interpretable coefficients to verify directional signs
        (e.g., does a larger FVG actually increase the probability of target?).
        """
        if not self.is_trained:
            return {}
        
        importances = {
            "target_model_coeffs": dict(zip(feature_names, self.model_target.coef_[0])),
            "stop_model_coeffs": dict(zip(feature_names, self.model_stop.coef_[0]))
        }
        return importances
