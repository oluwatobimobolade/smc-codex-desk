from typing import Dict, Any

class AbstentionGate:
    """
    Implements the certainty gate logic. A prediction becomes actionable 
    only when all strict conditions pass.
    """
    
    def __init__(self, 
                 max_ood_score: float = 1.0, 
                 max_disagreement: float = 0.10,
                 min_effective_samples: int = 100):
        self.max_ood_score = max_ood_score
        self.max_disagreement = max_disagreement
        self.min_effective_samples = min_effective_samples

    def evaluate_decision(self, prediction_data: Dict[str, Any]) -> str:
        """
        Evaluates the hard promotion gates. Returns the decision string.
        """
        # 1. Market Data & Scope
        if not prediction_data.get("in_scope", False):
            return "OUT_OF_SCOPE"
            
        if prediction_data.get("perception_status") != "validated":
            return "INSUFFICIENT_CONTEXT"
            
        # 2. Statistical Support
        if prediction_data.get("effective_similar_cases", 0) < self.min_effective_samples:
            return "LOW_SAMPLE_SUPPORT"
            
        # 3. Model Disagreement
        if prediction_data.get("model_disagreement", 1.0) > self.max_disagreement:
            return "MODEL_DISAGREEMENT"
            
        # 4. Out of Distribution
        if prediction_data.get("ood_score", 1.0) > self.max_ood_score:
            return "UNCALIBRATED_REGIME"
            
        # 5. Expectancy
        if prediction_data.get("expected_r_lower_95", -1.0) <= 0.0:
            return "NEGATIVE_EXPECTANCY"
            
        # If all pass, we allow it.
        # In later stages, this becomes ACTIONABLE. For now, PAPER_SHADOW_ONLY.
        return "PAPER_SHADOW_ONLY"
