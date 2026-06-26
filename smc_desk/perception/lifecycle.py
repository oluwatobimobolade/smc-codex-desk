from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

from smc_desk.perception.ontology import ConfirmationStatus, ActivityStatus, MitigationStatus, TerminalReason, SMCObjectBase


class EventType(str, Enum):
    OBJECT_CREATED = "OBJECT_CREATED"
    OBJECT_CONFIRMED = "OBJECT_CONFIRMED"
    OBJECT_ACTIVATED = "OBJECT_ACTIVATED"
    OBJECT_FIRST_TOUCHED = "OBJECT_FIRST_TOUCHED"
    OBJECT_PARTIALLY_MITIGATED = "OBJECT_PARTIALLY_MITIGATED"
    OBJECT_FULLY_MITIGATED = "OBJECT_FULLY_MITIGATED"
    OBJECT_INVALIDATED = "OBJECT_INVALIDATED"
    OBJECT_SUPERSEDED = "OBJECT_SUPERSEDED"


class SMCEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    event_type: EventType
    timestamp: datetime
    trigger_candle_id: str
    details: Optional[str] = None


def _event_value(event: SMCEvent | dict, key: str):
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key)


def apply_event(obj: SMCObjectBase, event: SMCEvent) -> None:
    """Applies a single event to the object, updating its derived status fields."""
    if not hasattr(obj, "events"):
        obj.events = []

    event_key = (event.event_type, event.timestamp, event.trigger_candle_id, event.details)
    for existing in obj.events:
        existing_key = (
            _event_value(existing, "event_type"),
            _event_value(existing, "timestamp"),
            _event_value(existing, "trigger_candle_id"),
            _event_value(existing, "details"),
        )
        if existing_key == event_key:
            return
    
    # State transition checks
    if obj.activity_status == ActivityStatus.TERMINAL and getattr(obj, "_last_event_type", None) != event.event_type:
        raise ValueError(f"Cannot transition: Object {obj.object_id} is already in TERMINAL state.")

    has_created = any(_event_value(ev, "event_type") == EventType.OBJECT_CREATED for ev in obj.events)
    has_confirmed = any(_event_value(ev, "event_type") == EventType.OBJECT_CONFIRMED for ev in obj.events)
    if event.event_type != EventType.OBJECT_CREATED and not has_created:
        raise ValueError(f"Cannot transition: Object {obj.object_id} has not been created.")
    if event.event_type == EventType.OBJECT_ACTIVATED and not has_confirmed:
        raise ValueError(f"Cannot transition: Object {obj.object_id} must be CONFIRMED before activation.")
        
    if event.event_type in (EventType.OBJECT_PARTIALLY_MITIGATED, EventType.OBJECT_FULLY_MITIGATED):
        if obj.activity_status != ActivityStatus.ACTIVE:
            raise ValueError(f"Cannot transition: Object {obj.object_id} must be ACTIVE to be mitigated.")
            
    obj.events.append(event)
    obj.current_as_of = event.timestamp
    setattr(obj, "_last_event_type", event.event_type)
    
    if event.event_type == EventType.OBJECT_CREATED:
        obj.confirmation_status = ConfirmationStatus.CANDIDATE
        obj.activity_status = ActivityStatus.INACTIVE
    elif event.event_type == EventType.OBJECT_CONFIRMED:
        obj.confirmation_status = ConfirmationStatus.CONFIRMED
        obj.confirmed_at = event.timestamp
    elif event.event_type == EventType.OBJECT_ACTIVATED:
        obj.activity_status = ActivityStatus.ACTIVE
    elif event.event_type == EventType.OBJECT_PARTIALLY_MITIGATED:
        obj.mitigation_status = MitigationStatus.PARTIAL
    elif event.event_type == EventType.OBJECT_FULLY_MITIGATED:
        obj.mitigation_status = MitigationStatus.FULL
        obj.activity_status = ActivityStatus.TERMINAL
        if obj.terminal_reason == TerminalReason.NONE:
            obj.terminal_reason = TerminalReason.CONSUMED
    elif event.event_type == EventType.OBJECT_INVALIDATED:
        obj.confirmation_status = ConfirmationStatus.REJECTED
        obj.activity_status = ActivityStatus.TERMINAL
        obj.terminal_reason = TerminalReason.INVALIDATED
    elif event.event_type == EventType.OBJECT_SUPERSEDED:
        obj.activity_status = ActivityStatus.TERMINAL
        obj.terminal_reason = TerminalReason.SUPERSEDED

def replay_events(obj: SMCObjectBase, events: List[SMCEvent]) -> None:
    """Replays a history of events to derive current object status."""
    for ev in events:
        apply_event(obj, ev)
