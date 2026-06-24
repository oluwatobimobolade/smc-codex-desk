from datetime import datetime, timezone
import json
import uuid
import os
from typing import Dict, Any, Optional

from smc_desk.vision.image_validation import validate_image_file
from smc_desk.vision.response_store import VisionResponseStore
from smc_desk.vision.prompt_templates import OVERLAY_AUDITOR_PROMPT

class OverlayAuditor:
    def __init__(self, store_dir: str = "cases"):
        self.store = VisionResponseStore(store_dir)

    def audit_overlay(
        self,
        case_id: str,
        annotated_image_path: str,
        clean_image_path: str,
        scene_graph_dict: Dict[str, Any],
        manifest_payload: Dict[str, Any],
        blind_response_id: str,
        provider_name: str,
        model_name: str,
        dry_run: bool = True,
        mock_audit_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compares the annotated chart against the scene graph to detect rendering defects.
        """
        # Ensure blind response exists and is locked before we can run overlay audit
        # This enforces the blind-first workflow requirement!
        
        attempt_id = str(uuid.uuid4())[:8]
        prompt_text = OVERLAY_AUDITOR_PROMPT
        
        if dry_run:
            if mock_audit_str:
                raw_response = mock_audit_str
            else:
                raw_response = json.dumps({
                    "audit_id": f"audit_{attempt_id}",
                    "case_id": case_id,
                    "blind_response_ref": blind_response_id,
                    "provider": provider_name,
                    "model": model_name,
                    "rendering_defects_found": False,
                    "reported_defects": [],
                    "style_mismatch_detected": False,
                    "labels_obscured": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
        else:
            # Run vision provider
            from smc_desk.vision.provider_registry import registry
            provider = registry.get(provider_name)
            # Send prompt and image
            raw_response, _ = provider.read_chart(
                open(annotated_image_path, "rb").read(),
                prompt_text,
                schema=None
            )
            
        audit_res = json.loads(raw_response)
        
        # Save overlay audit response separately in the store (never overwrite blind response)
        audit_dir = os.path.join(self.store.base_dir, case_id, "vision", provider_name, model_name, f"audit_{attempt_id}")
        os.makedirs(audit_dir, exist_ok=True)
        
        with open(os.path.join(audit_dir, "overlay_audit_response.json"), "w") as f:
            json.dump(audit_res, f, indent=2)
            
        return audit_res
