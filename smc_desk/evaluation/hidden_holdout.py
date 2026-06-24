import os
import json
import hashlib
from typing import Dict, Any, Optional

class HiddenHoldoutSet:
    def __init__(self, base_dir: str = ".holdout_cache"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def register_case(self, case_id: str, df_json: str, expected_annotations_json: str) -> str:
        """
        Stores a holdout case, hashes its content, and saves it immutably.
        """
        case_dir = os.path.join(self.base_dir, case_id)
        os.makedirs(case_dir, exist_ok=True)
        
        data_path = os.path.join(case_dir, "data.json")
        expected_path = os.path.join(case_dir, "expected.json")
        meta_path = os.path.join(case_dir, "meta.json")
        
        with open(data_path, "w") as f:
            f.write(df_json)
            
        with open(expected_path, "w") as f:
            f.write(expected_annotations_json)
            
        # Hashes to prevent leakage / tampering
        data_hash = hashlib.sha256(df_json.encode()).hexdigest()
        expected_hash = hashlib.sha256(expected_annotations_json.encode()).hexdigest()
        
        meta = {
            "case_id": case_id,
            "data_hash": data_hash,
            "expected_hash": expected_hash,
            "consumed": False,
            "registered_at": "2026-06-24T00:00:00Z"
        }
        
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
            
        return data_hash

    def verify_holdout_integrity(self, case_id: str) -> bool:
        case_dir = os.path.join(self.base_dir, case_id)
        meta_path = os.path.join(case_dir, "meta.json")
        if not os.path.exists(meta_path):
            return False
            
        with open(meta_path, "r") as f:
            meta = json.load(f)
            
        # Recompute hash
        with open(os.path.join(case_dir, "data.json"), "r") as f:
            data = f.read()
        recomputed = hashlib.sha256(data.encode()).hexdigest()
        
        return recomputed == meta["data_hash"]
