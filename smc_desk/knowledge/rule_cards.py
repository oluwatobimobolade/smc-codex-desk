from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class SupportType(str, Enum):
    DIRECT_SUPPORT = "direct_support"
    PARTIAL_SUPPORT = "partial_support"
    IMPLIED_ONLY = "implied_only"
    CONTRADICTED = "contradicted"
    NO_SUPPORT = "no_support"
    AMBIGUOUS = "ambiguous"

class RuleCard(BaseModel):
    rule_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex)
    concept: str
    academy: str
    exact_definition: str
    required_conditions: List[str] = Field(default_factory=list)
    optional_conditions: List[str] = Field(default_factory=list)
    invalidating_conditions: List[str] = Field(default_factory=list)
    positive_example: Optional[str] = None
    negative_example: Optional[str] = None
    ambiguous_example: Optional[str] = None
    timeframe_assumptions: List[str] = Field(default_factory=list)
    wick_versus_close_rule: str  # e.g., "body_close", "wick_probe", "either"
    source_references: List[str] = Field(default_factory=list)  # IDs of SourceRecords
    conflicts_with_other_academies: List[str] = Field(default_factory=list)
    confidence_in_extraction: float = 1.0
    # Reproducible source span evidence
    source_start_offset: Optional[int] = None
    source_end_offset: Optional[int] = None
    exact_extracted_span: Optional[str] = None
    span_hash: Optional[str] = None
    support_type: Optional[SupportType] = None
    critic_explanation: Optional[str] = None
