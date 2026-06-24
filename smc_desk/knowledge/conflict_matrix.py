from typing import List, Dict, Tuple
from pydantic import BaseModel
from smc_desk.knowledge.rule_cards import RuleCard

class RuleConflict(BaseModel):
    concept: str
    academy_a: str
    academy_b: str
    description: str
    resolution_guide: str

class ConflictMatrix:
    def __init__(self):
        self.conflicts: List[RuleConflict] = []

    def detect_conflicts(self, card_a: RuleCard, card_b: RuleCard) -> None:
        """Compares two rule cards for logical conflicts and adds to matrix."""
        if card_a.concept == card_b.concept and card_a.academy != card_b.academy:
            # Check wick/body close rule mismatch
            if card_a.wick_versus_close_rule != card_b.wick_versus_close_rule:
                self.conflicts.append(
                    RuleConflict(
                        concept=card_a.concept,
                        academy_a=card_a.academy,
                        academy_b=card_b.academy,
                        description=f"Wick vs close rule mismatch: {card_a.academy} uses '{card_a.wick_versus_close_rule}' while {card_b.academy} uses '{card_b.wick_versus_close_rule}'.",
                        resolution_guide="Evaluate under both rulebooks separately rather than merging."
                    )
                )
            
            # Check differing required conditions
            diff_conds_a = set(card_a.required_conditions) - set(card_b.required_conditions)
            diff_conds_b = set(card_b.required_conditions) - set(card_a.required_conditions)
            if diff_conds_a or diff_conds_b:
                self.conflicts.append(
                    RuleConflict(
                        concept=card_a.concept,
                        academy_a=card_a.academy,
                        academy_b=card_b.academy,
                        description=f"Required conditions differ. {card_a.academy} requires {diff_conds_a}, {card_b.academy} requires {diff_conds_b}.",
                        resolution_guide="Tag and track these objects separate relative to their active rule profiles."
                    )
                )

    def get_conflicts_for_concept(self, concept: str) -> List[RuleConflict]:
        return [c for c in self.conflicts if c.concept == concept]
