from typing import Optional, Dict
from pydantic import BaseModel, Field, model_validator

class PredictionContract(BaseModel):
    """
    Strict contract for an SMC probabilistic outcome forecast.
    Enforces the exclusion of vague binary win/loss targets.
    """
    setup_id: str = Field(..., description="Unique identifier for the setup (e.g. BTCUSDT-15M-2026-00182)")
    perception_status: str = Field(..., description="Validation status of the perception objects")
    state: str = Field(..., description="SMC Sequence state (e.g. RETRACE_CONFIRMED)")
    regime: str = Field(..., description="Current market regime definition")
    in_scope: bool = Field(..., description="Whether this prediction is within the certified scope")
    
    # Prediction specifics
    target: str = Field(..., description="The precise target event (e.g. external_buy_side_liquidity)")
    invalidation: str = Field(..., description="The precise invalidation event (e.g. protected_low)")
    horizon_bars: int = Field(..., description="Maximum number of bars until resolution")
    
    p_target_first: float = Field(..., ge=0, le=1, description="Probability target is reached before invalidation")
    p_stop_first: float = Field(..., ge=0, le=1, description="Probability invalidation is reached before target")
    p_unresolved: float = Field(..., ge=0, le=1, description="Probability neither occurs before expiry")
    
    p_target_lower_95: float = Field(..., ge=0, le=1, description="95% lower bound for target probability")
    expected_r: float = Field(..., description="Expected value in R units after fees and slippage")
    expected_r_lower_95: float = Field(..., description="95% lower bound for expected R")
    
    # Reliability metrics
    effective_similar_cases: int = Field(..., description="Number of effective similar cases observed")
    calibration_bin_observed_rate: float = Field(..., description="Historical observed rate in this calibration bin")
    brier_score_recent: float = Field(..., description="Recent Brier score for reliability tracking")
    model_disagreement: float = Field(..., description="Metric of disagreement between models")
    ood_score: float = Field(..., description="Out-of-distribution distance score")
    
    decision: str = Field(..., description="The final decision (e.g. ACTIONABLE, MODEL_DISAGREEMENT, INSUFFICIENT_CONTEXT)")
    reason: str = Field(..., description="Justification for the decision")

    @model_validator(mode="after")
    def probabilities_must_partition_outcomes(self) -> "PredictionContract":
        total = self.p_target_first + self.p_stop_first + self.p_unresolved
        if abs(total - 1.0) > 1e-6:
            raise ValueError("p_target_first + p_stop_first + p_unresolved must sum to 1.0")
        if self.p_target_lower_95 > self.p_target_first:
            raise ValueError("p_target_lower_95 cannot exceed p_target_first")
        return self
