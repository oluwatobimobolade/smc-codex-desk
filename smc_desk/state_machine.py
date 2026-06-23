"""Deterministic setup narratives for research replay.

This module deliberately does not replace the snapshot engine. It records the
sequence a setup followed so an experimental entry model can be tested without
changing the frozen baseline or quietly using future information.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class SetupState(str, Enum):
    WATCHING = "WATCHING"
    SWEEP_DETECTED = "SWEEP_DETECTED"
    DISPLACED = "DISPLACED"
    POI_ACTIVE = "POI_ACTIVE"
    EXECUTE = "EXECUTE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class StateMachineConfig:
    displacement_timeout_bars: int = 3
    retrace_timeout_bars: int = 48
    confirmation_timeout_bars: int = 24

    def __post_init__(self) -> None:
        if min(
            self.displacement_timeout_bars,
            self.retrace_timeout_bars,
            self.confirmation_timeout_bars,
        ) < 1:
            raise ValueError("State-machine timeouts must be at least one bar.")


@dataclass(frozen=True)
class PoiAnchor:
    kind: str
    low: float
    high: float
    source_bar_index: int
    score: float

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError("POI low must not exceed POI high.")


@dataclass(frozen=True)
class StateInput:
    symbol: str
    timeframe: str
    bar_index: int
    timestamp: str
    htf_direction: str = "neutral"
    sweep_direction: str | None = None
    sweep_price: float | None = None
    displacement_direction: str | None = None
    displacement_price: float | None = None
    candidate_poi: PoiAnchor | None = None
    poi_touched: bool = False
    poi_fully_mitigated: bool = False
    sweep_invalidated: bool = False
    confirmation: bool = False
    confirmation_name: str | None = None


@dataclass(frozen=True)
class SetupMemory:
    attempt_id: str
    symbol: str
    timeframe: str
    direction: str
    state: SetupState
    created_bar_index: int
    created_at: str
    last_bar_index: int
    sweep_bar_index: int
    sweep_price: float
    displacement_bar_index: int | None = None
    displacement_price: float | None = None
    poi: PoiAnchor | None = None
    poi_touched_bar_index: int | None = None
    confirmation_bar_index: int | None = None
    confirmation_name: str | None = None


@dataclass(frozen=True)
class StateTransition:
    attempt_id: str
    from_state: SetupState
    to_state: SetupState
    bar_index: int
    timestamp: str
    reason: str


@dataclass(frozen=True)
class StateUpdate:
    active_setup: SetupMemory | None
    transitions: tuple[StateTransition, ...] = ()

    @property
    def display_state(self) -> SetupState:
        return self.active_setup.state if self.active_setup is not None else SetupState.WATCHING

    @property
    def transition(self) -> StateTransition | None:
        """Compatibility shortcut for consumers interested in the latest event."""
        return self.transitions[-1] if self.transitions else None


def _is_direction(value: str | None) -> bool:
    return value in {"bullish", "bearish"}


def _transition(memory: SetupMemory, state: SetupState, event: StateInput, reason: str) -> StateTransition:
    return StateTransition(
        attempt_id=memory.attempt_id,
        from_state=memory.state,
        to_state=state,
        bar_index=event.bar_index,
        timestamp=event.timestamp,
        reason=reason,
    )


def _terminal(memory: SetupMemory, state: SetupState, event: StateInput, reason: str) -> StateUpdate:
    return StateUpdate(active_setup=None, transitions=(_transition(memory, state, event, reason),))


def _new_setup(event: StateInput) -> StateUpdate:
    if not (
        _is_direction(event.htf_direction)
        and event.sweep_direction == event.htf_direction
        and event.sweep_price is not None
    ):
        return StateUpdate(active_setup=None)
    direction = str(event.sweep_direction)
    memory = SetupMemory(
        attempt_id=f"{event.symbol}:{event.timeframe}:{event.bar_index}:{direction}",
        symbol=event.symbol,
        timeframe=event.timeframe,
        direction=direction,
        state=SetupState.SWEEP_DETECTED,
        created_bar_index=event.bar_index,
        created_at=event.timestamp,
        last_bar_index=event.bar_index,
        sweep_bar_index=event.bar_index,
        sweep_price=float(event.sweep_price),
    )
    return StateUpdate(
        active_setup=memory,
        transitions=(StateTransition(
            attempt_id=memory.attempt_id,
            from_state=SetupState.WATCHING,
            to_state=SetupState.SWEEP_DETECTED,
            bar_index=event.bar_index,
            timestamp=event.timestamp,
            reason="aligned_htf_liquidity_sweep",
        ),),
    )


def _validate_event(memory: SetupMemory, event: StateInput) -> None:
    if event.symbol != memory.symbol or event.timeframe != memory.timeframe:
        raise ValueError("State input symbol/timeframe must match the active setup.")
    if event.bar_index < memory.last_bar_index:
        raise ValueError("State inputs must be processed in chronological order.")


def advance_setup(
    event: StateInput,
    active_setup: SetupMemory | None,
    config: StateMachineConfig | None = None,
) -> StateUpdate:
    """Advance one closed-candle setup state without creating a trade plan.

    An eligible POI must be selected on the displacement candle. This freezes
    the object before the retrace and prevents replay from choosing a later,
    better-looking POI with hindsight.
    """
    config = config or StateMachineConfig()
    if active_setup is None:
        fresh = _new_setup(event)
        # A sweep and reversal/displacement can complete on one closed candle.
        # Preserve both transitions so the narrative does not lose the sweep.
        if fresh.active_setup is not None and event.displacement_direction is not None:
            progressed = advance_setup(event, fresh.active_setup, config)
            return StateUpdate(
                active_setup=progressed.active_setup,
                transitions=fresh.transitions + progressed.transitions,
            )
        return fresh

    _validate_event(active_setup, event)
    memory = replace(active_setup, last_bar_index=event.bar_index)

    if memory.state == SetupState.SWEEP_DETECTED:
        if event.bar_index > memory.sweep_bar_index + config.displacement_timeout_bars:
            return _terminal(memory, SetupState.EXPIRED, event, "displacement_timeout")
        if event.displacement_direction == memory.direction and event.displacement_price is not None:
            if event.candidate_poi is None:
                return _terminal(memory, SetupState.EXPIRED, event, "no_eligible_poi_on_displacement")
            displaced = replace(
                memory,
                state=SetupState.DISPLACED,
                displacement_bar_index=event.bar_index,
                displacement_price=float(event.displacement_price),
                poi=event.candidate_poi,
            )
            return StateUpdate(
                active_setup=displaced,
                transitions=(_transition(memory, SetupState.DISPLACED, event, "displacement_after_sweep"),),
            )
        return StateUpdate(active_setup=memory)

    if memory.state == SetupState.DISPLACED:
        if event.sweep_invalidated:
            return _terminal(memory, SetupState.INVALIDATED, event, "sweep_extreme_broken")
        if memory.displacement_bar_index is None or memory.poi is None:
            return _terminal(memory, SetupState.EXPIRED, event, "incomplete_displacement_memory")
        if event.bar_index > memory.displacement_bar_index + config.retrace_timeout_bars:
            return _terminal(memory, SetupState.EXPIRED, event, "retrace_timeout")
        if event.poi_fully_mitigated:
            return _terminal(memory, SetupState.INVALIDATED, event, "poi_fully_mitigated_before_entry")
        if event.poi_touched:
            poi_active = replace(memory, state=SetupState.POI_ACTIVE, poi_touched_bar_index=event.bar_index)
            return StateUpdate(
                active_setup=poi_active,
                transitions=(_transition(memory, SetupState.POI_ACTIVE, event, "price_entered_frozen_poi"),),
            )
        return StateUpdate(active_setup=memory)

    if memory.state == SetupState.POI_ACTIVE:
        if event.sweep_invalidated or event.poi_fully_mitigated:
            return _terminal(memory, SetupState.INVALIDATED, event, "poi_or_sweep_invalidated")
        if memory.poi_touched_bar_index is None:
            return _terminal(memory, SetupState.EXPIRED, event, "missing_poi_touch_memory")
        if event.bar_index > memory.poi_touched_bar_index + config.confirmation_timeout_bars:
            return _terminal(memory, SetupState.EXPIRED, event, "confirmation_timeout")
        if event.confirmation:
            execute = replace(
                memory,
                state=SetupState.EXECUTE,
                confirmation_bar_index=event.bar_index,
                confirmation_name=event.confirmation_name,
            )
            return StateUpdate(
                active_setup=execute,
                transitions=(_transition(memory, SetupState.EXECUTE, event, "confirmed_at_poi"),),
            )
        return StateUpdate(active_setup=memory)

    return StateUpdate(active_setup=memory)
