"""Generic strategy-state engine.

Consumes the canonical event ledger, MTF graph, and an optional strategy
transition contract to produce a StrategyStateResult. This engine is
strategy-neutral — specific strategies provide the transition rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, FrozenSet, List, Optional

from smc_desk.decision.contracts import (
    Direction,
    StateTransition,
    StrategyStateResult,
    TraderState,
)


@dataclass(frozen=True)
class TransitionRule:
    """One rule in a strategy's transition contract.

    from_state=None means this rule matches any non-terminal state.
    """

    rule_id: str
    from_state: Optional[TraderState]
    to_state: TraderState
    required_event_types: FrozenSet[str]
    required_conditions: FrozenSet[str]
    blocking_conditions: FrozenSet[str]


@dataclass(frozen=True)
class StrategyContract:
    """A strategy's complete transition contract."""

    strategy_id: str
    strategy_version: str
    rules: List[TransitionRule]

    def find_rule(
        self, from_state: TraderState, to_state: TraderState
    ) -> Optional[TransitionRule]:
        for rule in self.rules:
            if rule.from_state == from_state and rule.to_state == to_state:
                return rule
        return None


# ── Research observation contract (no real strategy) ──

RESEARCH_OBSERVATION = StrategyContract(
    strategy_id="NONE",
    strategy_version="0.0.0",
    rules=[
        TransitionRule(
            rule_id="none_to_observe",
            from_state=TraderState.NO_SETUP,
            to_state=TraderState.CONTEXT_FORMING,
            required_event_types=frozenset(),
            required_conditions=frozenset({"mtf_graph_valid"}),
            blocking_conditions=frozenset({"insufficient_data", "stale_candles"}),
        ),
        TransitionRule(
            rule_id="observe_to_watch",
            from_state=TraderState.CONTEXT_FORMING,
            to_state=TraderState.WATCH,
            required_event_types=frozenset({"SWING_CONFIRMED", "STRUCTURE_BREAK_CANDIDATE"}),
            required_conditions=frozenset({"mtf_graph_valid", "dual_timeframe_aligned"}),
            blocking_conditions=frozenset({"genuine_contradiction", "insufficient_history"}),
        ),
        TransitionRule(
            rule_id="watch_to_armed",
            from_state=TraderState.WATCH,
            to_state=TraderState.ARMED,
            required_event_types=frozenset(
                {"SWING_CONFIRMED", "STRUCTURE_BREAK_CONFIRMED", "FVG_CREATED"}
            ),
            required_conditions=frozenset({"price_near_active_fvg"}),
            blocking_conditions=frozenset({"genuine_contradiction"}),
        ),
        TransitionRule(
            rule_id="armed_to_triggered",
            from_state=TraderState.ARMED,
            to_state=TraderState.TRIGGERED,
            required_event_types=frozenset({"STRUCTURE_BREAK_CONFIRMED"}),
            required_conditions=frozenset({"internal_break_confirmed"}),
            blocking_conditions=frozenset(),
        ),
        TransitionRule(
            rule_id="any_to_invalidated",
            from_state=None,  # sentinel: matches any non-terminal state
            to_state=TraderState.INVALIDATED,
            required_event_types=frozenset(),
            required_conditions=frozenset({"sweep_invalidated_or_poi_mitigated"}),
            blocking_conditions=frozenset(),
        ),
        TransitionRule(
            rule_id="any_to_expired",
            from_state=None,
            to_state=TraderState.EXPIRED,
            required_event_types=frozenset(),
            required_conditions=frozenset({"timeout"}),
            blocking_conditions=frozenset(),
        ),
    ],
)


class StateEngine:
    """Generic strategy-state engine. Strategy-neutral by design."""

    def __init__(self, contract: StrategyContract = RESEARCH_OBSERVATION):
        self.contract = contract
        self._state = TraderState.NO_SETUP
        self._transition_history: List[StateTransition] = []
        self._event_ids_seen: set = set()

    @property
    def current_state(self) -> TraderState:
        return self._state

    @property
    def history(self) -> List[StateTransition]:
        return list(self._transition_history)

    def reset(self) -> None:
        self._state = TraderState.NO_SETUP
        self._transition_history.clear()
        self._event_ids_seen.clear()

    def evaluate(
        self,
        event_types: set[str],
        conditions_met: set[str],
        direction: Direction = Direction.NEUTRAL,
        timestamp: Optional[datetime] = None,
    ) -> StrategyStateResult:
        """Evaluate the current state against available evidence.

        Returns a StrategyStateResult. Duplicate evaluations with identical
        conditions DO NOT advance the state (idempotent).
        """
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)

        # Check for invalidating conditions first
        for rule in self.contract.rules:
            if rule.to_state != TraderState.INVALIDATED:
                continue
            if self._state in (TraderState.INVALIDATED, TraderState.RESOLVED):
                continue
            requires = {r for r in rule.required_conditions
                       if r in conditions_met}
            blocks = {b for b in rule.blocking_conditions
                     if b in conditions_met}
            if requires and not blocks:
                self._record_transition(
                    TraderState.INVALIDATED, rule.rule_id, [], timestamp
                )
                self._state = TraderState.INVALIDATED
                return self._build_result(direction, timestamp)

        # Check for other transitions
        allowed = TraderState.allowed_transitions().get(self._state, frozenset())
        best_rule: Optional[TransitionRule] = None
        best_score = -1

        for rule in self.contract.rules:
            if rule.to_state == TraderState.INVALIDATED:
                continue
            matches_from = (
                rule.from_state is None
                or rule.from_state == self._state
            )
            # None (any-match) only for non-terminal states
            if rule.from_state is None and self._state in (
                TraderState.INVALIDATED, TraderState.EXPIRED, TraderState.RESOLVED
            ):
                continue
            if not matches_from:
                continue
            if rule.to_state not in allowed:
                continue

            required = {r for r in rule.required_event_types
                       if r in event_types}
            conds = {c for c in rule.required_conditions
                    if c in conditions_met}
            blocks = {b for b in rule.blocking_conditions
                     if b in conditions_met}

            score = len(required) + len(conds)
            if score > best_score and not blocks:
                best_score = score
                best_rule = rule

        if best_rule is not None and best_rule.to_state != self._state:
            self._record_transition(
                best_rule.to_state, best_rule.rule_id, [], timestamp
            )
            self._state = best_rule.to_state

        return self._build_result(direction, timestamp)

    def _record_transition(
        self,
        to_state: TraderState,
        rule_id: str,
        event_ids: List[str],
        timestamp: datetime,
    ) -> None:
        t = StateTransition(
            from_state=self._state,
            to_state=to_state,
            timestamp=timestamp,
            rule_id=rule_id,
            triggering_event_ids=event_ids,
        )
        self._transition_history.append(t)

    def _build_result(
        self, direction: Direction, timestamp: datetime
    ) -> StrategyStateResult:
        prev = (
            self._transition_history[-2].from_state
            if len(self._transition_history) >= 2
            else TraderState.NO_SETUP
        )
        last_rule = (
            self._transition_history[-1].rule_id
            if self._transition_history
            else "none"
        )
        return StrategyStateResult(
            strategy_id=self.contract.strategy_id,
            strategy_version=self.contract.strategy_version,
            state=self._state,
            previous_state=prev,
            transition_rule_id=last_rule,
            transition_time=timestamp,
            supporting_event_ids=[],
            blocking_conditions=[],
            missing_conditions=[],
            invalidation_conditions=["TIME_OR_INVALIDATION"],
            expiry_condition=None,
            direction=direction,
            authority_mode="research_observation",
        )
