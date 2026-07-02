import json
import logging
from typing import Dict, Any

class LiveShadowLogger:
    """
    Handles the recording of frozen, pre-outcome predictions during live shadow 
    execution for final untouchable holdout evaluation.
    """
    def __init__(self, log_path: str = "logs/live_shadow_predictions.jsonl"):
        self.log_path = log_path
        # Setup specific logger to ensure atomic writes to the JSONL file
        self.logger = logging.getLogger("live_shadow")
        handler = logging.FileHandler(self.log_path)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
    def record_prediction(self, prediction_contract: Dict[str, Any]) -> None:
        """
        Records the exact prediction state BEFORE the outcome is known.
        This provides the cryptographic-style proof that the model was not curve-fit.
        """
        # Ensure it's a valid contract (stub validation)
        if "setup_id" not in prediction_contract or "decision" not in prediction_contract:
            raise ValueError("Invalid prediction contract format.")
            
        # Write exact JSON record
        self.logger.info(json.dumps(prediction_contract))
