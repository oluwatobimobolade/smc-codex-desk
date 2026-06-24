from datetime import datetime, timezone
import uuid
import json
from typing import Dict, Any, Optional

from smc_desk.vision.schemas import VisionResponse, MetadataRead
from smc_desk.vision.provider_registry import registry
from smc_desk.vision.image_validation import validate_image_file
from smc_desk.vision.response_store import VisionResponseStore
from smc_desk.vision.prompt_templates import BLIND_READER_PROMPT, get_prompt_hash

class BlindReader:
    def __init__(self, store_dir: str = "cases"):
        self.store = VisionResponseStore(store_dir)

    def read_blindly(
        self,
        case_id: str,
        image_path: str,
        provider_name: str,
        model_name: str,
        manifest_payload: Dict[str, Any],
        dry_run: bool = True,
        mock_response_str: Optional[str] = None
    ) -> VisionResponse:
        """
        Executes the blind-first reading process, validating the clean image
        and locking the structured response immutable.
        """
        # 1. Enforce blind review check: check image path is not annotated, verify hash and dimensions
        expected_hash = manifest_payload.get("image_hash")
        expected_width = manifest_payload.get("chart_width")
        expected_height = manifest_payload.get("chart_height")
        val_report = validate_image_file(
            image_path,
            expected_hash=expected_hash,
            expected_width=expected_width,
            expected_height=expected_height,
            is_review_mode=True
        )
        if not val_report["valid"]:
            raise ValueError(f"Clean review image validation failed: {val_report['errors']}")


        attempt_id = str(uuid.uuid4())[:8]
        prompt_text = BLIND_READER_PROMPT
        
        # 2. Get provider response
        if dry_run:
            # Generate synthetic response conforming to schema
            if mock_response_str:
                raw_response = mock_response_str
            else:
                raw_response = json.dumps({
                    "response_id": f"resp_{attempt_id}",
                    "case_id": case_id,
                    "provider": provider_name,
                    "model": model_name,
                    "prompt_version": "1.0.0",
                    "schema_version": "1.0.0",
                    "chart_valid": True,
                    "metadata_read": {
                        "symbol": "BTCUSDT",
                        "timeframe": "15m",
                        "venue": "binance",
                        "latest_visible_timestamp": "2026-06-23T12:00:00Z",
                        "scale_type": "linear",
                        "price_labels_legible": True,
                        "time_labels_legible": True,
                        "is_cropped": False,
                        "indicators_obscure_price": False
                    },
                    "structure_read": "bearish",
                    "detected_objects": [
                        {
                            "vision_object_id": "v_obj_1",
                            "object_type": "swing_high",
                            "direction": "bearish",
                            "confidence": 0.85,
                            "evidence_description": "Clear pivot high rejected from 21400",
                            "ambiguous": False
                        }
                    ],
                    "overall_confidence": 0.8,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
        else:
            provider = registry.get(provider_name)
            raw_response, run_meta = provider.read_chart(
                open(image_path, "rb").read(),
                prompt_text,
                schema=VisionResponse
            )
            
        # 3. Parse and Validate Schema
        response_dict = json.loads(raw_response)
        parsed_response = VisionResponse.model_validate(response_dict)
        
        # 4. Save and Lock
        self.store.save_attempt(
            case_id=case_id,
            provider=provider_name,
            model=model_name,
            attempt_id=attempt_id,
            prompt_text=prompt_text,
            image_manifest=manifest_payload,
            raw_response=raw_response,
            parsed_response_dict=parsed_response.model_dump(mode="json"),
            validation_report=val_report
        )
        
        return parsed_response
