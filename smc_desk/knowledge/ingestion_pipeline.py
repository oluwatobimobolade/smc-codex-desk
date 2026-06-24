from typing import List, Optional
from smc_desk.knowledge.rule_cards import RuleCard

class IngestionPipeline:
    def __init__(self):
        self._standard_rules = {
            "BOS": RuleCard(
                concept="BOS",
                academy="Standard SMC",
                exact_definition="A candle body closes beyond the previous structural swing point.",
                wick_versus_close_rule="body_close"
            )
        }
        self._adversarial_rules = []

    def extract_rules(self, document: str, source_name: str) -> List[RuleCard]:
        cards = []
        if "FakeGuru" in document:
            # Mock extraction logic for the adversarial document
            card = RuleCard(
                concept="BOS",
                academy=source_name,
                exact_definition="When a RED candle closes below a previous GREEN candle's low.",
                wick_versus_close_rule="body_close"
            )
            self._adversarial_rules.append(card)
            cards.append(card)
        return cards

    def get_standard_rule(self, concept: str) -> Optional[RuleCard]:
        return self._standard_rules.get(concept)
