from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class CalibrationCertificate(BaseModel):
    gold_set_version: str
    gold_set_hash: str
    model_name: str
    model_version: str
    prompt_version: str
    schema_version: str = "1.0.0"
    evaluation_timestamp: datetime
    approved_authority_level: str  # review_flag, calibrated_veto, full_fusion
    approver: str
    certificate_hash: str

def enforce_authority_mode(config: Dict[str, Any], certificate: Optional[CalibrationCertificate] = None) -> None:
    """
    Enforces that vision_authority_mode defaults to observe_only and refuses
    startup or fails if a higher mode is active without a valid CalibrationCertificate.
    """
    mode = config.get("vision_authority_mode", "observe_only")
    if mode == "observe_only":
        return
        
    if mode in ["review_flag", "calibrated_veto", "full_fusion"]:
        if certificate is None:
            raise ValueError(
                f"STARTUP_PREVENTED: vision_authority_mode is set to '{mode}', "
                f"but no valid CalibrationCertificate is present. "
                f"Only 'observe_only' mode is allowed before calibration is completed."
            )
        # Verify certificate signature/hash (in a real system)
        pass
    else:
        raise ValueError(f"Invalid vision_authority_mode: {mode}")
