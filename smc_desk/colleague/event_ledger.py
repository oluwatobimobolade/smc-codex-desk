"""Canonical event ledger for PEV2 perception objects.

Converts PEV2 PerceptionSnapshot into an immutable, append-only event stream.
Each event represents a discrete occurrence, not a state. The ledger is the
single source of truth for the decision pipeline.

Event types:
- SWING_CONFIRMED: a swing was confirmed at a specific time
- STRUCTURE_BREAK_CANDIDATE: a wick penetrated a protected level
- STRUCTURE_BREAK_CONFIRMED: a body closed beyond a protected level (BOS/CHoCH)
- FVG_CREATED: a fair value gap formed
- FVG_MITIGATED: a FVG was partially or fully mitigated
- FVG_INVALIDATED: a FVG was invalidated

Each event is deterministic: same input → same output.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.perception.ontology import (
    FairValueGapObject,
    StructureBreakObject,
    SwingObject,
)


class EventType(str, Enum):
    SWING_CONFIRMED = "SWING_CONFIRMED"
    STRUCTURE_BREAK_CANDIDATE = "STRUCTURE_BREAK_CANDIDATE"
    STRUCTURE_BREAK_CONFIRMED = "STRUCTURE_BREAK_CONFIRMED"
    FVG_CREATED = "FVG_CREATED"
    FVG_MITIGATED = "FVG_MITIGATED"
    FVG_INVALIDATED = "FVG_INVALIDATED"


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    event_id: str
    event_type: EventType
    timeframe: str
    occurred_at: datetime
    available_at: datetime
    object_ids: List[str]
    source_candle_ids: List[str]
    ontology_version: str
    provisional: bool
    metadata: Dict[str, str]


class EventLedger(BaseModel):
    """Immutable, append-only event stream derived from PEV2 perception."""

    model_config = ConfigDict(use_enum_values=True)

    events: List[CanonicalEvent]
    decision_time: datetime
    ontology_version: str

    @classmethod
    def from_snapshot(
        cls,
        snapshot: PerceptionSnapshot,
        ontology_version: str = "2.0.0",
    ) -> EventLedger:
        """Convert a PerceptionSnapshot into a canonical event ledger.

        The conversion is deterministic: same snapshot → same ledger.
        Events are sorted by available_at, then by event_type, then by object_id.
        """
        events: List[CanonicalEvent] = []

        # Extract swing confirmation events
        for scale, swings in snapshot.swings.items():
            for swing in swings:
                event = _swing_to_event(swing, scale, ontology_version)
                events.append(event)

        # Extract structure break events
        for brk in snapshot.structure_breaks:
            # Candidate break (wick penetration)
            candidate_event = _break_to_candidate_event(brk, ontology_version)
            events.append(candidate_event)

            # Confirmed break (body close) if confirmed
            if str(brk.confirmation_status).lower() == "confirmed":
                confirmed_event = _break_to_confirmed_event(brk, ontology_version)
                events.append(confirmed_event)

        # Extract FVG events
        for fvg in snapshot.fvgs:
            created_event = _fvg_to_created_event(fvg, ontology_version)
            events.append(created_event)

            # Check mitigation/invalidation status
            if fvg.evidence.is_mitigated_on_creation:
                mitigated_event = _fvg_to_mitigated_event(fvg, ontology_version)
                events.append(mitigated_event)

        # Sort by available_at, then event_type, then object_id for determinism
        events.sort(key=lambda e: (e.available_at, e.event_type, e.object_ids[0] if e.object_ids else ""))

        return cls(
            events=events,
            decision_time=snapshot.decision_time,
            ontology_version=ontology_version,
        )


def _make_event_id(event_type: EventType, object_id: str, timestamp: datetime) -> str:
    """Generate a deterministic event ID."""
    raw = f"{event_type.value}:{object_id}:{timestamp.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _swing_to_event(swing: SwingObject, scale: str, ontology_version: str) -> CanonicalEvent:
    """Convert a SwingObject to a SWING_CONFIRMED event."""
    occurred_at = swing.pivot_time
    available_at = swing.confirmed_at if swing.confirmed_at else swing.pivot_time

    return CanonicalEvent(
        event_id=_make_event_id(EventType.SWING_CONFIRMED, swing.object_id, available_at),
        event_type=EventType.SWING_CONFIRMED,
        timeframe=swing.timeframe,
        occurred_at=occurred_at,
        available_at=available_at,
        object_ids=[swing.object_id],
        source_candle_ids=swing.source_candle_ids,
        ontology_version=ontology_version,
        provisional=False,
        metadata={
            "direction": swing.direction,
            "scale": scale,
            "price_high": str(swing.price_high),
            "price_low": str(swing.price_low),
        },
    )


def _break_to_candidate_event(brk: StructureBreakObject, ontology_version: str) -> CanonicalEvent:
    """Convert a StructureBreakObject to a STRUCTURE_BREAK_CANDIDATE event."""
    occurred_at = brk.candidate_at
    available_at = brk.candidate_at  # candidate is known at candle open
    
    # Infer break_type from is_choch flag
    break_type = "CHOCH" if brk.is_choch else "BOS"

    return CanonicalEvent(
        event_id=_make_event_id(EventType.STRUCTURE_BREAK_CANDIDATE, brk.object_id, available_at),
        event_type=EventType.STRUCTURE_BREAK_CANDIDATE,
        timeframe=brk.timeframe,
        occurred_at=occurred_at,
        available_at=available_at,
        object_ids=[brk.object_id],
        source_candle_ids=brk.source_candle_ids,
        ontology_version=ontology_version,
        provisional=True,
        metadata={
            "break_type": break_type,
            "direction": brk.direction,
            "broken_price": str(brk.evidence.broken_price),
            "wick_penetration": str(brk.evidence.wick_penetration),
        },
    )


def _break_to_confirmed_event(brk: StructureBreakObject, ontology_version: str) -> CanonicalEvent:
    """Convert a confirmed StructureBreakObject to a STRUCTURE_BREAK_CONFIRMED event."""
    occurred_at = brk.confirmed_at if brk.confirmed_at else brk.candidate_at
    available_at = brk.confirmed_at if brk.confirmed_at else brk.candidate_at
    
    # Infer break_type from is_choch flag
    break_type = "CHOCH" if brk.is_choch else "BOS"

    return CanonicalEvent(
        event_id=_make_event_id(EventType.STRUCTURE_BREAK_CONFIRMED, brk.object_id, available_at),
        event_type=EventType.STRUCTURE_BREAK_CONFIRMED,
        timeframe=brk.timeframe,
        occurred_at=occurred_at,
        available_at=available_at,
        object_ids=[brk.object_id],
        source_candle_ids=brk.source_candle_ids,
        ontology_version=ontology_version,
        provisional=False,
        metadata={
            "break_type": break_type,
            "direction": brk.direction,
            "broken_price": str(brk.evidence.broken_price),
            "body_close_penetration": str(brk.evidence.body_close_penetration),
        },
    )


def _fvg_to_created_event(fvg: FairValueGapObject, ontology_version: str) -> CanonicalEvent:
    """Convert a FairValueGapObject to a FVG_CREATED event."""
    occurred_at = fvg.pivot_time
    available_at = fvg.confirmed_at if fvg.confirmed_at else fvg.pivot_time

    return CanonicalEvent(
        event_id=_make_event_id(EventType.FVG_CREATED, fvg.object_id, available_at),
        event_type=EventType.FVG_CREATED,
        timeframe=fvg.timeframe,
        occurred_at=occurred_at,
        available_at=available_at,
        object_ids=[fvg.object_id],
        source_candle_ids=fvg.source_candle_ids,
        ontology_version=ontology_version,
        provisional=False,
        metadata={
            "direction": fvg.direction,
            "price_high": str(fvg.price_high),
            "price_low": str(fvg.price_low),
            "gap_size_bps": str(fvg.evidence.gap_size_bps),
        },
    )


def _fvg_to_mitigated_event(fvg: FairValueGapObject, ontology_version: str) -> CanonicalEvent:
    """Convert a mitigated FairValueGapObject to a FVG_MITIGATED event."""
    # Use confirmed_at as the mitigation time (when it was first mitigated)
    mitigated_at = fvg.confirmed_at if fvg.confirmed_at else fvg.pivot_time

    return CanonicalEvent(
        event_id=_make_event_id(EventType.FVG_MITIGATED, fvg.object_id, mitigated_at),
        event_type=EventType.FVG_MITIGATED,
        timeframe=fvg.timeframe,
        occurred_at=mitigated_at,
        available_at=mitigated_at,
        object_ids=[fvg.object_id],
        source_candle_ids=fvg.source_candle_ids,
        ontology_version=ontology_version,
        provisional=False,
        metadata={
            "direction": fvg.direction,
            "price_high": str(fvg.price_high),
            "price_low": str(fvg.price_low),
        },
    )
