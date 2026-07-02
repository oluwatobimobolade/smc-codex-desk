import numpy as np
import pandas as pd

try:
    from sklearn.neighbors import LocalOutlierFactor
except ImportError:
    pass

class OutOfDistributionDetector:
    """
    Calculates distance metrics from the training distribution to 
    reject novel or uncalibrated market regimes.
    """
    def __init__(self):
        # We use LOF as a standard anomaly detection mechanism for OOD
        self.detector = LocalOutlierFactor(n_neighbors=20, novelty=True)
        self.is_fitted = False
        
    def fit(self, X_train: pd.DataFrame) -> None:
        """
        Fits the distribution of the training data.
        """
        self.detector.fit(X_train)
        self.is_fitted = True
        
    def score_samples(self, X_new: pd.DataFrame) -> np.ndarray:
        """
        Returns an OOD score. Lower values (negative) indicate higher outlierness.
        We convert it to a positive distance metric where higher means more OOD.
        """
        if not self.is_fitted:
            raise ValueError("OOD Detector is not fitted.")
            
        # LOF returns negative values for outliers
        scores = self.detector.decision_function(X_new)
        # Invert so higher is more anomalous, zero-bounded
        ood_scores = np.maximum(0, -scores)
        return ood_scores
