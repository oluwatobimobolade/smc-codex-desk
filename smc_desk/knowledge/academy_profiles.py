from typing import Dict, List
from pydantic import BaseModel, Field
from smc_desk.knowledge.rule_cards import RuleCard

class AcademyProfile(BaseModel):
    name: str
    description: str
    rules: Dict[str, RuleCard] = Field(default_factory=dict)

# Curation of Rule presets for testing Phase 5
ACADEMIES: Dict[str, AcademyProfile] = {
    "ICT-V1": AcademyProfile(
        name="ICT-V1",
        description="Inner Circle Trader style rules",
        rules={
            "fvg": RuleCard(
                concept="fvg",
                academy="ICT-V1",
                exact_definition="3-candle imbalance where candle 1 high does not overlap candle 3 low (or vice versa).",
                required_conditions=["impulsive candle 2 body size", "no overlap between c1 and c3"],
                wick_versus_close_rule="either",
                confidence_in_extraction=1.0
            ),
            "order_block": RuleCard(
                concept="order_block",
                academy="ICT-V1",
                exact_definition="Last opposing candle before displacement that breaks structure, requiring an FVG.",
                required_conditions=["displacement", "breaks structure", "has adjacent FVG"],
                wick_versus_close_rule="body_close",
                confidence_in_extraction=0.95
            )
        }
    ),
    "Consensus-V2": AcademyProfile(
        name="Consensus-V2",
        description="Strict body closure confirmation rules",
        rules={
            "bos": RuleCard(
                concept="bos",
                academy="Consensus-V2",
                exact_definition="Confirmed body close beyond the established swing high or low.",
                required_conditions=["body_close_penetration > 0", "valid swing high/low references"],
                wick_versus_close_rule="body_close",
                confidence_in_extraction=1.0
            )
        }
    ),
    "Hierarchical-Swing-V1": AcademyProfile(
        name="Hierarchical-Swing-V1",
        description="Structure swing significance levels",
        rules={
            "swing": RuleCard(
                concept="swing",
                academy="Hierarchical-Swing-V1",
                exact_definition="Pivot points confirmed via multi-scale candle range checks (local, internal, external).",
                required_conditions=["pivot_time <= confirmed_at"],
                wick_versus_close_rule="either",
                confidence_in_extraction=1.0
            )
        }
    )
}

def get_academy_profile(name: str) -> AcademyProfile:
    if name not in ACADEMIES:
        raise ValueError(f"Academy profile '{name}' not found.")
    return ACADEMIES[name]
