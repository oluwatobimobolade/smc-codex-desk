import json
import base64
import hashlib
from datetime import datetime, timezone
from typing import Tuple, Any

from anthropic import Anthropic

from smc_desk.vision.provider_interface import VisionProviderInterface, ProviderRunMetadata

class ClaudeVisionProvider(VisionProviderInterface):
    """
    Anthropic Claude 3.5 Sonnet Vision Provider.
    Extracts the VisionRead schema from the image.
    """
    def __init__(self, api_key: str = None, model: str = "claude-3-5-sonnet-20241022"):
        self._provider_name = "anthropic"
        self._model_name = model
        # Using the standard SDK. If api_key is None, it defaults to the ANTHROPIC_API_KEY env var
        self.client = Anthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def read_chart(self, image_bytes: bytes, prompt: str, schema: Any) -> Tuple[str, ProviderRunMetadata]:
        req_time = datetime.now(timezone.utc)
        
        # Prepare base64 image
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        system_prompt = "You are a professional SMC trading analyst and computer vision expert. "
        if hasattr(schema, "model_json_schema"):
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            system_prompt += f"\nYou must output ONLY valid JSON conforming to this schema:\n{schema_json}"
            
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_image
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
        
        # In a real environment, we'd use tool use to enforce schema, but JSON mode prompt works for fallback
        response = self.client.messages.create(
            model=self._model_name,
            max_tokens=2048,
            temperature=0.0,
            system=system_prompt,
            messages=messages
        )
        
        raw_text = response.content[0].text
        res_time = datetime.now(timezone.utc)
        
        raw_hash = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()
        
        metadata = ProviderRunMetadata(
            provider_name=self.provider_name,
            model_name=self.model_name,
            model_version=self._model_name,
            request_id=response.id,
            temperature=0.0,
            prompt_version="v1",
            request_timestamp=req_time,
            response_timestamp=res_time,
            token_usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens
            },
            raw_response_hash=raw_hash,
            parsed_response_hash=raw_hash  # Usually hash of parsed dict, kept simple here
        )
        
        return raw_text, metadata
