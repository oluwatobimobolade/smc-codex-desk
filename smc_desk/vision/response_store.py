import os
import json
import hashlib
from typing import Any, Dict

class VisionResponseStore:
    def __init__(self, base_dir: str = "cases"):
        self.base_dir = base_dir

    def get_attempt_dir(self, case_id: str, provider: str, model: str, attempt_id: str) -> str:
        return os.path.join(self.base_dir, case_id, "vision", provider, model, attempt_id)

    def save_attempt(
        self,
        case_id: str,
        provider: str,
        model: str,
        attempt_id: str,
        prompt_text: str,
        image_manifest: Dict[str, Any],
        raw_response: str,
        parsed_response_dict: Dict[str, Any],
        validation_report: Dict[str, Any]
    ) -> str:
        """
        Saves all files for a vision provider attempt and locks it.
        """
        attempt_dir = self.get_attempt_dir(case_id, provider, model, attempt_id)
        os.makedirs(attempt_dir, exist_ok=True)
        
        prompt_path = os.path.join(attempt_dir, "prompt.txt")
        manifest_path = os.path.join(attempt_dir, "image_manifest.json")
        raw_path = os.path.join(attempt_dir, "raw_response.json")
        parsed_path = os.path.join(attempt_dir, "parsed_response.json")
        val_path = os.path.join(attempt_dir, "validation_report.json")
        hashes_path = os.path.join(attempt_dir, "hashes.json")
        
        # Write files
        with open(prompt_path, "w") as f:
            f.write(prompt_text)
            
        with open(manifest_path, "w") as f:
            json.dump(image_manifest, f, indent=2)
            
        # Raw response might be pure string or json, save as raw string/json
        try:
            raw_json = json.loads(raw_response)
            with open(raw_path, "w") as f:
                json.dump(raw_json, f, indent=2)
        except json.JSONDecodeError:
            with open(raw_path, "w") as f:
                f.write(raw_response)
                
        with open(parsed_path, "w") as f:
            json.dump(parsed_response_dict, f, indent=2)
            
        with open(val_path, "w") as f:
            json.dump(validation_report, f, indent=2)
            
        # Compute hashes for lock
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        manifest_hash = hashlib.sha256(json.dumps(image_manifest).encode()).hexdigest()
        raw_hash = hashlib.sha256(raw_response.encode()).hexdigest()
        parsed_hash = hashlib.sha256(json.dumps(parsed_response_dict).encode()).hexdigest()
        
        hashes = {
            "prompt_hash": prompt_hash,
            "manifest_hash": manifest_hash,
            "raw_response_hash": raw_hash,
            "parsed_response_hash": parsed_hash,
            "lock_status": "locked",
            "immutable": True
        }
        
        with open(hashes_path, "w") as f:
            json.dump(hashes, f, indent=2)
            
        return attempt_dir

    def is_locked(self, case_id: str, provider: str, model: str, attempt_id: str) -> bool:
        attempt_dir = self.get_attempt_dir(case_id, provider, model, attempt_id)
        hashes_path = os.path.join(attempt_dir, "hashes.json")
        if os.path.exists(hashes_path):
            with open(hashes_path, "r") as f:
                hashes = json.load(f)
                return hashes.get("immutable", False)
        return False
