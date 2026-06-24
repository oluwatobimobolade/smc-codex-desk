import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class GoldSetLabel(BaseModel):
    """A human-adjudicated label for an SMC Object."""
    object_id: str
    object_type: str
    annotator_id: str
    agreed_status: str  # confirmed, rejected, ambiguous
    # Dictionary containing the actual object fields agreed upon by humans
    ground_truth_evidence: dict
    notes: Optional[str] = None

class GoldSetCase(BaseModel):
    """A single evaluation case (e.g., 2 weeks of 15m BTCUSDT) with its gold labels."""
    case_id: str
    venue: str
    instrument: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    
    # Path to the raw OHLCV data used for this case
    data_path: str
    
    # Human labels
    labels: List[GoldSetLabel] = []
    
    # Adjudication status
    is_fully_adjudicated: bool = False
    
    def save(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"{self.case_id}.json"
        with open(file_path, "w") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, file_path: Path) -> "GoldSetCase":
        with open(file_path, "r") as f:
            return cls.model_validate_json(f.read())

class GoldSetManager:
    """Manages the lifecycle of gold set cases (definition, pilot, validation)."""
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.definition_dir = self.base_dir / "definition_set"
        self.pilot_dir = self.base_dir / "pilot_set"
        self.validation_dir = self.base_dir / "validation_set"
        
        self.definition_dir.mkdir(parents=True, exist_ok=True)
        self.pilot_dir.mkdir(parents=True, exist_ok=True)
        self.validation_dir.mkdir(parents=True, exist_ok=True)

    def list_cases(self, subset: str) -> List[GoldSetCase]:
        target_dir = getattr(self, f"{subset}_dir")
        cases = []
        for file in target_dir.glob("*.json"):
            cases.append(GoldSetCase.load(file))
        return cases
