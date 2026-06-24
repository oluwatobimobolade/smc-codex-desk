from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
import hashlib
from typing import Optional

class AgentExecutionRecord(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str
    provider_account: Optional[str] = None
    model_identifier: str
    model_version: str
    request_id: Optional[str] = None
    prompt_hash: str
    retrieval_context_hash: Optional[str] = None
    temperature: float
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prior_outputs_visible: bool = False
    agent_role: str
    request_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response_hash: Optional[str] = None

    @property
    def provider_model_key(self) -> str:
        """Returns a string representing the unique provider and model combination."""
        return f"{self.provider}/{self.model_identifier}"

    @classmethod
    def compute_hash(cls, content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
