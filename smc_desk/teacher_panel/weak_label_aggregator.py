from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class LabelTier(str, Enum):
    BRONZE_AI = "bronze_ai"
    SILVER_AI_CONSENSUS = "silver_ai_consensus"
    SILVER_HIGH_CONFIDENCE = "silver_high_confidence"
    GOLD_OBJECTIVE_ORACLE = "gold_objective_oracle"
    GOLD_HUMAN_ADJUDICATED = "gold_human_adjudicated"
    DISPUTED = "disputed"
    REJECTED = "rejected"

class WeakLabelAggregator:
    def __init__(self):
        pass

    def classify_label(
        self,
        proposal: Dict[str, Any],
        independent_opinions: List[Dict[str, Any]],  # Decisions from multiple models
        numerical_verified: bool,
        rule_verified: bool,
        extractor_key: Optional[str] = None,
        critic_key: Optional[str] = None,
        annotator_conversation_id: Optional[str] = None,
        judge_conversation_ids: Optional[List[str]] = None,
        human_adjudication: Optional[Dict[str, Any]] = None
    ) -> LabelTier:
        """
        Classifies the label quality level based on the strict quality gates.
        """
        if extractor_key and critic_key:
            assert extractor_key != critic_key, "Independence violation: Extractor and Critic share provider/model"
            
        if annotator_conversation_id and judge_conversation_ids:
            for j_cid in judge_conversation_ids:
                assert j_cid != annotator_conversation_id, "Independence violation: Annotator and Judge share conversation context"

        approved_opinions = [op for op in independent_opinions if op.get("approved")]
        total_opinions = len(independent_opinions)

        if human_adjudication:
            if human_adjudication.get("approved"):
                return LabelTier.GOLD_HUMAN_ADJUDICATED
            else:
                return LabelTier.REJECTED

        if total_opinions > 0 and len(approved_opinions) < (total_opinions / 2):
            return LabelTier.REJECTED

        if total_opinions >= 3 and len(approved_opinions) == total_opinions:
            if numerical_verified and rule_verified:
                return LabelTier.SILVER_HIGH_CONFIDENCE
            else:
                return LabelTier.SILVER_AI_CONSENSUS

        if total_opinions >= 3 and len(approved_opinions) > (total_opinions / 2):
            return LabelTier.DISPUTED

        return LabelTier.BRONZE_AI
