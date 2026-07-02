import numpy as np

class UncertaintyQuantifier:
    """
    Computes distinct axes of uncertainty (Perception, Data, Model, Market) 
    and calculates conservative lower bounds.
    """
    
    @staticmethod
    def calculate_p_target_lower_95(p_target: float, n_effective_samples: int) -> float:
        """
        Calculates the 95% lower confidence bound for a binomial proportion
        using a Wilson score interval or similar conservative bound.
        """
        if n_effective_samples <= 0:
            return 0.0
            
        z = 1.96 # 95% confidence
        # Wilson score interval lower bound
        denominator = 1 + z**2 / n_effective_samples
        center = p_target + z**2 / (2 * n_effective_samples)
        spread = z * np.sqrt((p_target * (1 - p_target) + z**2 / (4 * n_effective_samples)) / n_effective_samples)
        
        lower_bound = (center - spread) / denominator
        return max(0.0, lower_bound)

    @staticmethod
    def calculate_expected_r_lower_95(p_target_lower_95: float, 
                                      p_stop_upper_95: float, 
                                      target_r: float, 
                                      stop_r: float = -1.0) -> float:
        """
        Calculates the conservative lower bound of expected R.
        EV = (P_win * Target_R) + (P_loss * Stop_R)
        We use the lower bound for win and upper bound for loss to be extremely conservative.
        """
        return (p_target_lower_95 * target_r) + (p_stop_upper_95 * stop_r)
        
    @staticmethod
    def quantify_model_disagreement(p_model_a: float, p_model_b: float) -> float:
        """
        Returns the absolute divergence between the baseline and the complex model.
        """
        return abs(p_model_a - p_model_b)
