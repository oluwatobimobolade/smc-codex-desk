"""SMC Decision Contracts — typed strategy states, transitions, and evidence.

This package provides the generic trader decision machinery. It does NOT
implement any specific strategy (RASC, etc.). It provides the contracts
that specific strategies plug into.

Design principles:
- PEV2 is perception authority, NOT trading authority.
- The state engine is generic; strategy rules are external contracts.
- No PAPER_EXECUTE until a certified strategy runtime exists.
- Conservative output: ABSTAIN when uncertain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set


class TraderState(str, Enum):
    """Generic trader states. Strategy-specific rules control transitions."""

    NO_SETUP = "NO_SETUP"
    CONTEXT_FORMING = "CONTEXT_FORMING"
    WATCH = "WATCH"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    RESOLVED = "RESOLVED"
    ABSTAIN = "ABSTAIN"

    @classmethod
    def allowed_transitions(cls) -> Dict[str, FrozenSet[str]]:
        """All state transitions. Strategy contracts can restrict further."""
        return {
            cls.NO_SETUP: frozenset({cls.CONTEXT_FORMING, cls.ABSTAIN}),
            cls.CONTEXT_FORMING: frozenset({cls.WATCH, cls.NO_SETUP, cls.ABSTAIN, cls.EXPIRED}),
            cls.WATCH: frozenset({cls.ARMED, cls.ABSTAIN, cls.EXPIRED, cls.NO_SETUP}),
            cls.ARMED: frozenset({cls.TRIGGERED, cls.ABSTAIN, cls.EXPIRED, cls.WATCH, cls.INVALIDATED}),
            cls.TRIGGERED: frozenset({cls.INVALIDATED, cls.EXPIRED, cls.RESOLVED, cls.ABSTAIN}),
            cls.INVALIDATED: frozenset({cls.NO_SETUP, cls.ABSTAIN}),
            cls.EXPIRED: frozenset({cls.NO_SETUP, cls.ABSTAIN}),
            cls.RESOLVED: frozenset({cls.NO_SETUP, cls.ABSTAIN}),
            cls.ABSTAIN: frozenset({cls.NO_SETUP, cls.CONTEXT_FORMING, cls.WATCH}),
        }


class Decision(str, Enum):
    """Final decision action. Conservative by design."""

    ABSTAIN = "ABSTAIN"
    OBSERVE = "OBSERVE"
    WATCH = "WATCH"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class StateTransition:
    """A single state transition record."""

    from_state: TraderState
    to_state: TraderState
    timestamp: datetime
    rule_id: str  # which strategy rule caused this transition
    triggering_event_ids: List[str]
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyStateResult:
    """The output of the strategy-state engine for one decision time."""

    strategy_id: str  # "NONE" when no active strategy
    strategy_version: str
    state: TraderState
    previous_state: TraderState
    transition_rule_id: str
    transition_time: datetime
    supporting_event_ids: List[str]
    blocking_conditions: List[str]
    missing_conditions: List[str]
    invalidation_conditions: List[str]
    expiry_condition: Optional[str]
    direction: Direction = Direction.NEUTRAL
    authority_mode: str = "research_observation"


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence supporting or opposing a scenario."""

    evidence_id: str
    evidence_type: str  # "supporting", "opposing", "missing"
    description: str
    event_ids: List[str]
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class ScenarioResult:
    """A single scenario with full evidence graph."""

    scenario_id: str
    claim: str
    direction: Direction
    state: TraderState
    supporting: List[EvidenceItem]
    opposing: List[EvidenceItem]
    missing: List[EvidenceItem]
    confirmation_events: List[str]
    invalidation_events: List[str]
    expiry_condition: Optional[str]
    authority_status: str = "research_observation"


@dataclass(frozen=True)
class DecisionEnvelope:
    """Final decision envelope produced by the decision policy."""

    decision: Decision
    direction: Direction
    state: TraderState
    strategy_id: str
    scenarios: List[ScenarioResult]
    reason: str
    authority: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
