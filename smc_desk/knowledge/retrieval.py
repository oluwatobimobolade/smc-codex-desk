from typing import List, Dict, Optional
from smc_desk.knowledge.rule_cards import RuleCard
from smc_desk.knowledge.academy_profiles import get_academy_profile, ACADEMIES

class RuleCardRetrieval:
    def __init__(self):
        # Index of rule cards by concept
        self._cards_by_concept: Dict[str, List[RuleCard]] = {}
        self._load_from_presets()

    def _load_from_presets(self):
        for profile in ACADEMIES.values():
            for card in profile.rules.values():
                self.add_rule_card(card)

    def add_rule_card(self, card: RuleCard) -> None:
        if card.concept not in self._cards_by_concept:
            self._cards_by_concept[card.concept] = []
        self._cards_by_concept[card.concept].append(card)

    def retrieve_by_concept(self, concept: str) -> List[RuleCard]:
        return self._cards_by_concept.get(concept, [])

    def retrieve_by_academy_and_concept(self, academy: str, concept: str) -> Optional[RuleCard]:
        cards = self.retrieve_by_concept(concept)
        for card in cards:
            if card.academy == academy:
                return card
        return None
