import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from smc_desk.data.schemas import Candle
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    StructureBreakEvidence,
    StructureBreakObject,
    SwingObject,
)


@dataclass
class _StructureTrack:
    scope: str
    current_direction: Optional[Direction] = None
    active_high: Optional[SwingObject] = None
    active_low: Optional[SwingObject] = None
    protected_high: Optional[SwingObject] = None
    protected_low: Optional[SwingObject] = None
    last_confirmed_high: Optional[SwingObject] = None
    last_confirmed_low: Optional[SwingObject] = None
    last_break: Optional[StructureBreakObject] = None
    last_bos_swing_id: Optional[str] = None
    pending: Dict[tuple[str, str], StructureBreakObject] = field(default_factory=dict)


class ProtectedStructureState:
    def __init__(self):
        self.current_direction: Optional[Direction] = None
        self.internal_direction: Optional[Direction] = None
        self.protected_high_id: Optional[str] = None
        self.protected_low_id: Optional[str] = None
        self.protected_internal_high_id: Optional[str] = None
        self.protected_internal_low_id: Optional[str] = None
        self.last_confirmed_external_high: Optional[str] = None
        self.last_confirmed_external_low: Optional[str] = None
        self.last_confirmed_internal_high: Optional[str] = None
        self.last_confirmed_internal_low: Optional[str] = None
        self.last_external_break: Optional[StructureBreakObject] = None
        self.last_internal_break: Optional[StructureBreakObject] = None
        self.current_as_of: Optional[datetime] = None


class StructureDetector:
    def __init__(self, detector_version: str = "2.0", structure_break_min_bps: float = 4.0):
        self.detector_version = detector_version
        self.structure_break_min_bps = structure_break_min_bps
        self.configuration_hash = hashlib.sha256(b"structure_v2_wp0022").hexdigest()[:8]

    def detect(
        self,
        candles: List[Candle],
        swings: List[SwingObject],
        current_time: datetime,
    ) -> Tuple[ProtectedStructureState, List[StructureBreakObject]]:
        state = ProtectedStructureState()
        breaks: list[StructureBreakObject] = []
        swings = sorted(swings, key=lambda s: s.pivot_time)

        confirmed_by_time: dict[datetime, list[tuple[str, SwingObject]]] = defaultdict(list)
        for swing in swings:
            if swing.confirmed_at is None:
                continue
            scope = _scope_for_swing(swing)
            if scope not in {"external", "internal"}:
                continue
            confirmed_by_time[swing.confirmed_at].append((scope, swing))

        tracks = {
            "external": _StructureTrack(scope="external"),
            "internal": _StructureTrack(scope="internal"),
        }

        for candle in candles:
            if candle.close_time > current_time:
                break
            state.current_as_of = candle.close_time

            for scope, swing in confirmed_by_time.get(candle.close_time, []):
                self._activate_swing(tracks[scope], swing, state)

            # External structure is processed first because it owns bias. Internal
            # structure is timing evidence and cannot overwrite external state.
            for scope in ("external", "internal"):
                breaks.extend(self._process_track_candle(tracks[scope], candle, state, current_time))

        return state, breaks

    def _activate_swing(self, track: _StructureTrack, swing: SwingObject, state: ProtectedStructureState) -> None:
        if swing.direction == Direction.BEARISH:
            track.active_high = swing
            track.last_confirmed_high = swing
            track.pending = {key: value for key, value in track.pending.items() if key[0] != Direction.BULLISH.value}
            if track.scope == "external":
                state.last_confirmed_external_high = swing.object_id
            else:
                state.last_confirmed_internal_high = swing.object_id
        else:
            track.active_low = swing
            track.last_confirmed_low = swing
            track.pending = {key: value for key, value in track.pending.items() if key[0] != Direction.BEARISH.value}
            if track.scope == "external":
                state.last_confirmed_external_low = swing.object_id
            else:
                state.last_confirmed_internal_low = swing.object_id

    def _process_track_candle(
        self,
        track: _StructureTrack,
        candle: Candle,
        state: ProtectedStructureState,
        current_time: datetime,
    ) -> list[StructureBreakObject]:
        created: list[StructureBreakObject] = []
        for direction, target in (
            (Direction.BULLISH, self._target_high(track)),
            (Direction.BEARISH, self._target_low(track)),
        ):
            if target is None:
                continue
            key = (direction.value, target.object_id)
            level = target.price_high if direction == Direction.BULLISH else target.price_low
            wick_crossed = candle.high > level if direction == Direction.BULLISH else candle.low < level
            if not wick_crossed:
                continue

            pending = track.pending.get(key)
            if pending is None:
                pending = self._create_break(candle, target, direction, state, current_time, track)
                if pending is None:
                    continue
                track.pending[key] = pending
                created.append(pending)

            body_confirmed = candle.close > level if direction == Direction.BULLISH else candle.close < level
            if body_confirmed and pending.confirmation_status == ConfirmationStatus.CANDIDATE:
                self._confirm_break(pending, candle, state, track, target)
                track.pending.pop(key, None)

        return created

    def _target_high(self, track: _StructureTrack) -> Optional[SwingObject]:
        if track.scope == "external" and track.current_direction == Direction.BEARISH and track.protected_high:
            return track.protected_high
        return track.active_high

    def _target_low(self, track: _StructureTrack) -> Optional[SwingObject]:
        if track.scope == "external" and track.current_direction == Direction.BULLISH and track.protected_low:
            return track.protected_low
        return track.active_low

    def _create_break(
        self,
        candle: Candle,
        broken_swing: SwingObject,
        direction: Direction,
        state: ProtectedStructureState,
        current_time: datetime,
        track: _StructureTrack,
    ) -> Optional[StructureBreakObject]:
        is_continuation = track.current_direction in {None, direction}
        broke_protected = broken_swing.object_id in {
            track.protected_high.object_id if track.protected_high else None,
            track.protected_low.object_id if track.protected_low else None,
        }
        if is_continuation:
            break_type = "BOS"
        else:
            break_type = "CHOCH" if (track.scope == "internal" or broke_protected) else "BOS"

        wick_pen = (
            candle.high - broken_swing.price_high
            if direction == Direction.BULLISH
            else broken_swing.price_low - candle.low
        )
        body_pen = (
            candle.close - broken_swing.price_high
            if direction == Direction.BULLISH
            else broken_swing.price_low - candle.close
        )
        broken_price = broken_swing.price_high if direction == Direction.BULLISH else broken_swing.price_low
        min_penetration = broken_price * Decimal(str(self.structure_break_min_bps / 10000.0))
        if wick_pen < min_penetration:
            return None

        candle_range = candle.high - candle.low
        body = candle.close - candle.open
        evidence = StructureBreakEvidence(
            broken_swing_id=broken_swing.object_id,
            broken_price=broken_price,
            wick_penetration=wick_pen,
            body_close_penetration=body_pen,
            penetration_ticks=int(wick_pen / Decimal("0.01")) if wick_pen > 0 else 0,
            penetration_atr_pct=0.0,
            candle_body_ratio=float(body / candle_range) if candle_range != 0 else 0.0,
            displacement_strength=0.0,
            is_internal=(track.scope == "internal"),
            is_unconfirmed_probe=True,
            structure_scope=track.scope,  # type: ignore[arg-type]
            protected_swing_id=broken_swing.object_id if broke_protected else None,
            last_bos_swing_id=track.last_bos_swing_id,
            broke_protected_swing=broke_protected,
            valid_choch=(break_type == "CHOCH" and (track.scope == "internal" or broke_protected)),
        )

        scope_token = "" if track.scope == "external" else "_internal"
        obj_id = f"{break_type}{scope_token}_{direction.value}_{candle.open_time.timestamp()}"
        brk = StructureBreakObject(
            object_id=obj_id,
            venue=candle.venue,
            instrument=candle.instrument,
            timeframe=candle.timeframe,
            pivot_time=broken_swing.pivot_time,
            candidate_at=candle.open_time,
            confirmed_at=None,
            current_as_of=current_time,
            schema_version="1.0.0",
            detector_version=self.detector_version,
            configuration_hash=self.configuration_hash,
            source_candle_ids=[f"c_{candle.open_time.timestamp()}"],
            last_updated_at=current_time,
            confidence=0.0,
            direction=direction,
            price_low=candle.low,
            price_high=candle.high,
            break_type=break_type,  # type: ignore[arg-type]
            structure_scope=track.scope,  # type: ignore[arg-type]
            evidence=evidence,
            confirmation_status=ConfirmationStatus.CANDIDATE,
            is_choch=(break_type == "CHOCH"),
        )

        apply_event(
            brk,
            SMCEvent(
                event_type=EventType.OBJECT_CREATED,
                timestamp=candle.open_time,
                trigger_candle_id=f"c_{candle.open_time.timestamp()}",
                details=f"{track.scope} wick penetration recorded as probe",
            ),
        )
        return brk

    def _confirm_break(
        self,
        brk: StructureBreakObject,
        candle: Candle,
        state: ProtectedStructureState,
        track: _StructureTrack,
        broken_swing: SwingObject,
    ) -> None:
        brk.evidence.is_unconfirmed_probe = False
        brk.evidence.body_close_penetration = (
            candle.close - brk.evidence.broken_price
            if brk.direction == Direction.BULLISH
            else brk.evidence.broken_price - candle.close
        )
        brk.source_candle_ids.append(f"c_{candle.open_time.timestamp()}")
        brk.confirmation_status = ConfirmationStatus.CONFIRMED
        brk.confirmed_at = candle.close_time
        apply_event(
            brk,
            SMCEvent(
                event_type=EventType.OBJECT_CONFIRMED,
                timestamp=candle.close_time,
                trigger_candle_id=f"c_{candle.open_time.timestamp()}",
                details="Body close confirmed structural break",
            ),
        )

        track.current_direction = brk.direction
        track.last_break = brk

        if brk.direction == Direction.BULLISH:
            track.protected_low = track.last_confirmed_low
            track.last_bos_swing_id = track.protected_low.object_id if track.protected_low else None
            if track.active_high and track.active_high.object_id == broken_swing.object_id:
                track.active_high = None
        else:
            track.protected_high = track.last_confirmed_high
            track.last_bos_swing_id = track.protected_high.object_id if track.protected_high else None
            if track.active_low and track.active_low.object_id == broken_swing.object_id:
                track.active_low = None

        if track.scope == "external":
            state.current_direction = track.current_direction
            state.protected_high_id = track.protected_high.object_id if track.protected_high else None
            state.protected_low_id = track.protected_low.object_id if track.protected_low else None
            state.last_external_break = brk
        else:
            state.internal_direction = track.current_direction
            state.protected_internal_high_id = track.protected_high.object_id if track.protected_high else None
            state.protected_internal_low_id = track.protected_low.object_id if track.protected_low else None
            state.last_internal_break = brk


def _scope_for_swing(swing: SwingObject) -> str:
    scale = getattr(swing.evidence, "scale_name", None)
    if scale in {"external", "internal", "local"}:
        return "external" if scale == "external" else "internal" if scale == "internal" else "local"
    return "external" if swing.evidence.is_external else "internal"
