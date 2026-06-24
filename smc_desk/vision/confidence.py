from typing import List
from smc_desk.vision.schemas import VisionResponse

class VisionConfidenceTracker:
    def sort_review_queue(self, responses: List[VisionResponse]) -> List[VisionResponse]:
        """
        Sorts the queue of responses so that the lowest confidence or highly
        ambiguous responses are reviewed first.
        """
        # Sort by overall_confidence ascending (lowest confidence first)
        # and prioritize abstained responses.
        return sorted(
            responses,
            key=lambda r: (0.0 if r.abstain else r.overall_confidence)
        )
