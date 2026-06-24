import json
import hashlib
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class PermissionsPolicy(BaseModel):
    storage_allowed: bool = False
    analysis_allowed: bool = False
    retrieval_allowed: bool = False
    fine_tuning_allowed: bool = False
    derivative_labels_allowed: bool = False

class SourceRecord(BaseModel):
    source_id: str
    academy: str
    educator: str
    content_title: str
    content_type: str  # video, article, course, licensed_file
    publication_date: Optional[str] = None
    video_timestamp: Optional[str] = None
    source_url: Optional[str] = None
    permission_status: str = "restricted"  # permitted, licensed, restricted
    concepts_covered: List[str] = Field(default_factory=list)
    chart_examples_available: bool = False
    future_outcome_visible: bool = False
    source_quality_tier: str = "Tier3"  # Tier1, Tier2, Tier3
    access_method: str = "manual"
    copyright_status: str = "unknown"
    ingestion_hash: str
    permissions: PermissionsPolicy = Field(default_factory=PermissionsPolicy)

    @classmethod
    def compute_hash(cls, content_bytes: bytes) -> str:
        return hashlib.sha256(content_bytes).hexdigest()

class SourceRegistry:
    def __init__(self):
        self._sources: Dict[str, SourceRecord] = {}

    def register_source(self, record: SourceRecord) -> None:
        self._sources[record.source_id] = record

    def get_source(self, source_id: str) -> Optional[SourceRecord]:
        return self._sources.get(source_id)

    def list_sources(self) -> List[SourceRecord]:
        return list(self._sources.values())
