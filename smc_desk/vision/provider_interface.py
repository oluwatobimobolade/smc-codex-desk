from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel

class ProviderRunMetadata(BaseModel):
    provider_name: str
    model_name: str
    model_version: str
    request_id: str
    temperature: float = 0.0
    seed: Optional[int] = None
    image_input_config: Dict[str, Any] = {}
    response_schema_version: str = "1.0.0"
    prompt_version: str
    request_timestamp: datetime
    response_timestamp: datetime
    token_usage: Dict[str, int] = {}
    raw_response_hash: str
    parsed_response_hash: str

class VisionProviderInterface(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def read_chart(self, image_bytes: bytes, prompt: str, schema: Any) -> Tuple[str, ProviderRunMetadata]:
        """
        Sends the image to the vision provider and returns the raw response string
        along with run metadata.
        """
        pass
