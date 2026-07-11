"""Inducement hypothesis state machine (programme §9).

Inducement is a FALSIFIABLE hypothesis, never a post-hoc unfalsifiable
explanation. Per programme §9.2, all five necessary conditions must hold:

    1. a deeper (higher-ranked) POI or objective exists;
    2. an intermediate visible liquidity or POI exists;
    3. a plausible causal path from shallow -> deeper exists;
    4. a structural reason the shallow object is weaker exists;
    5. unconsumed liquidity around the intermediate object exists.

The module emits INDUCEMENT_CANDIDATE only if ALL five hold, and records
the rejection event (what would falsify the hypothesis) so the critic can
test it. A hypothesis may be CONSUMED (deeper POI reached after shallow
interaction) or REJECTED (contradicting event).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

from smc_desk.data.hashing import object_sha256


class InducementState(str, Enum):
    NO_HYPOTHESIS = "no_inducement_hypothesis"
    CANDIDATE = "inducement_candidate"
    PATH_ACTIVE = "inducement_path_active"
    CONSUMED = "inducement_consumed"
    REJECTED = "hypothesis_rejected"


@dataclass(frozen=True)
class InducementHypothesis:
    hypothesis_id: str
    shallow_object_evidence_id: str
    deeper_object_evidence_id: str
    rejection_event_definition: str
    state: str                         # see InducementState
    conditions: dict[str, bool]        # the five necessary conditions
    rationale: str
    lifecycle: tuple[str, ...]        # ordered state transitions
    notes: tuple[str, ...] = ()
    schema: str = "inducement_hypothesis_v1"

    @property
    def sha256(self) -> str:
        return object_sha256({
            "hypothesis_id": self.hypothesis_id,
            "shallow_object_evidence_id": self.shallow_object_evidence_id,
            "deeper_object_evidence_id": self.deeper_object_evidence_id,
            "state": self.state,
            "conditions": self.conditions,
            "rejection_event_definition": self.rejection_event_definition,
        })


def evaluate(
    *,
    hypothesis_id: str,
    shallow_object_evidence_id: str,
    deeper_object_evidence_id: str,
    has_deeper_poi: bool,
    has_intermediate_visible_liquidity: bool,
    has_plausible_causal_path: bool,
    has_structural_reason_shallow_weaker: bool,
    has_unconsumed_liquidity_around_intermediate: bool,
    rejection_event_definition: str,
    rationale: str = "",
) -> InducementHypothesis:
    """Emit a hypothesis only if all five necessary conditions hold (§9.2)."""
    conditions = {
        "deeper_poi": has_deeper_poi,
        "intermediate_visible_liquidity": has_intermediate_visible_liquidity,
        "plausible_causal_path": has_plausible_causal_path,
        "structural_reason_shallow_weaker": has_structural_reason_shallow_weaker,
        "unconsumed_liquidity_around_intermediate": has_unconsumed_liquidity_around_intermediate,
    }
    all_hold = all(conditions.values())
    state = InducementState.CANDIDATE.value if all_hold else InducementState.NO_HYPOTHESIS.value
    return InducementHypothesis(
        hypothesis_id=hypothesis_id,
        shallow_object_evidence_id=shallow_object_evidence_id,
        deeper_object_evidence_id=deeper_object_evidence_id,
        rejection_event_definition=rejection_event_definition,
        state=state,
        conditions=conditions,
        rationale=rationale or (
            "All five §9.2 conditions satisfied -> INDUCEMENT_CANDIDATE."
            if all_hold else
            f"Hypothesis NOT emitted; failing conditions: "
            f"{[k for k,v in conditions.items() if not v]}."
        ),
        lifecycle=(InducementState.CANDIDATE.value,) if all_hold else (),
    )


def confirm_consumption(
    hyp: InducementHypothesis,
    *,
    intermediate_interacted: bool,
    deeper_reached: bool,
    no_contradicting_event: bool,
) -> InducementHypothesis:
    """Transition CANDIDATE -> PATH_ACTIVE -> CONSUMED.

    CONSUMED requires the intermediate was interacted with, the deeper POI
    was subsequently reached, and no contradicting event in between (§9.4).
    """
    if hyp.state == InducementState.NO_HYPOTHESIS.value:
        return hyp
    new_state = hyp.state
    lifecycle = tuple(hyp.lifecycle)
    if intermediate_interacted and hyp.state == InducementState.CANDIDATE.value:
        new_state = InducementState.PATH_ACTIVE.value
        lifecycle = lifecycle + (InducementState.PATH_ACTIVE.value,)
    if deeper_reached and no_contradicting_event and new_state == InducementState.PATH_ACTIVE.value:
        new_state = InducementState.CONSUMED.value
        lifecycle = lifecycle + (InducementState.CONSUMED.value,)
    if not (intermediate_interacted and deeper_reached and no_contradicting_event):
        # A contradicting event or deeper reached without intermediate -> reject
        new_state = InducementState.REJECTED.value
        lifecycle = lifecycle + (InducementState.REJECTED.value,)
    return InducementHypothesis(
        **{**asdict(hyp),
           "state": new_state,
           "lifecycle": lifecycle,
           "notes": tuple(hyp.notes) + (f"post-evaluation state={new_state}",)},
    )


__all__ = [
    "InducementState",
    "InducementHypothesis",
    "evaluate",
    "confirm_consumption",
]