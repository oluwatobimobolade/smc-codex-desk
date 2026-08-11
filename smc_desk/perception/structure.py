import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from smc_desk.data.schemas import Candle
from smc_desk.perception.causal_repair_flags import causal_protected_point_enabled
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
    # Every confirmed swing of this scope that price has NOT yet traded
    # through. The tracker used to hold a single active low and high, so a
    # candle sweeping five structural levels retired only one and the other
    # four stayed "live" in the model while price traded far beyond them.
    unbroken_lows: list[SwingObject] = field(default_factory=list)
    unbroken_highs: list[SwingObject] = field(default_factory=list)


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
                breaks.extend(self._process_track_candle(tracks[scope], candle, state, current_time, candles, swings))

        return state, breaks

    def _activate_swing(self, track: _StructureTrack, swing: SwingObject, state: ProtectedStructureState) -> None:
        if swing.direction == Direction.BEARISH:
            track.active_high = swing
            track.last_confirmed_high = swing
            track.unbroken_highs.append(swing)
            track.pending = {key: value for key, value in track.pending.items() if key[0] != Direction.BULLISH.value}
            if track.scope == "external":
                state.last_confirmed_external_high = swing.object_id
            else:
                state.last_confirmed_internal_high = swing.object_id
        else:
            track.active_low = swing
            track.last_confirmed_low = swing
            track.unbroken_lows.append(swing)
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
        candles: Sequence[Candle],
        swings: List[SwingObject],
    ) -> list[StructureBreakObject]:
        created: list[StructureBreakObject] = []
        confirmed_this_candle: list[StructureBreakObject] = []
        for direction, target in (
            (Direction.BULLISH, self._target_high(track)),
            (Direction.BEARISH, self._target_low(track)),
        ):
            if target is None:
                continue
            key = (direction.value, target.object_id)
            level = target.price_high if direction == Direction.BULLISH else target.price_low

            # A level price has ALREADY traded through cannot be broken again.
            #
            # A swing needs bars to its right before it confirms, so price can
            # crash through a low and only afterwards have that low become an
            # available target. Without this guard the very next candle
            # trivially satisfies `low < level` and a retroactive phantom break
            # is recorded -- on CADJPY 4H a "bearish BOS" of 115.871 was logged
            # at 20:00 on a candle ranging 113.755-114.332, four hours after
            # the 12:00 collapse had already taken price to 112.707, and while
            # price was moving up.
            #
            # A genuine break approaches from the correct side: the candle
            # opens on the level's protected side and closes through it.
            approached_correctly = (
                candle.open <= level if direction == Direction.BULLISH else candle.open >= level
            )
            if not approached_correctly:
                continue

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
                self._confirm_break(pending, candle, state, track, target, candles, swings, current_time)
                confirmed_this_candle.append(pending)
                track.pending.pop(key, None)

        # One violent candle can close through several structural levels at
        # once. Only the target above becomes a labelled structural event --
        # exploding one collapse into five BOS objects would be its own kind
        # of noise -- but every level it genuinely closed beyond must stop
        # being treated as live structure. Leaving them "unbroken" made the
        # model believe levels were intact while price traded far past them,
        # and let them resurface later as phantom targets.
        retired_count = self._retire_broken_levels(track, candle)
        # Magnitude belongs to the candle that BODY-CONFIRMED the break. A
        # delayed confirmation object was created on an earlier wick probe, so
        # assigning only to ``created`` silently left those events at zero.
        for brk in confirmed_this_candle:
            brk.evidence.levels_broken_by_candle = retired_count

        return created

    def _retire_broken_levels(self, track: _StructureTrack, candle: Candle) -> int:
        """Retire every level this candle BODY-CLOSED through. Returns the count."""
        before = len(track.unbroken_lows) + len(track.unbroken_highs)
        track.unbroken_lows = [
            swing for swing in track.unbroken_lows if candle.close >= swing.price_low
        ]
        track.unbroken_highs = [
            swing for swing in track.unbroken_highs if candle.close <= swing.price_high
        ]
        return before - (len(track.unbroken_lows) + len(track.unbroken_highs))

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
            # The candle that first crossed the level with a wick. Everything
            # else on this evidence object describes THIS candle until
            # _confirm_break records the confirming one separately.
            probe_candle_id=f"c_{candle.open_time.timestamp()}",
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
        candles: Sequence[Candle],
        swings: List[SwingObject],
        current_time: datetime,
    ) -> None:
        brk.evidence.is_unconfirmed_probe = False
        brk.evidence.body_close_penetration = (
            candle.close - brk.evidence.broken_price
            if brk.direction == Direction.BULLISH
            else brk.evidence.broken_price - candle.close
        )

        # WP-SMC-11 (audit F2): record the confirming candle's OWN geometry.
        # candle_body_ratio and the object's price_low/high belong to the probe
        # candle; without these fields a delayed confirmation would be scored
        # from two different candles at once.
        confirmation_id = f"c_{candle.open_time.timestamp()}"
        confirmation_range = candle.high - candle.low
        confirmation_body = abs(candle.close - candle.open)
        brk.evidence.body_close_candle_id = confirmation_id
        brk.evidence.is_delayed_confirmation = (
            brk.evidence.probe_candle_id is not None
            and brk.evidence.probe_candle_id != confirmation_id
        )
        brk.evidence.confirmation_candle_range = confirmation_range
        brk.evidence.confirmation_body_size = confirmation_body
        brk.evidence.confirmation_candle_body_ratio = (
            float(confirmation_body / confirmation_range) if confirmation_range > 0 else 0.0
        )

        brk.source_candle_ids.append(confirmation_id)
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

        # Legacy protected-point assignment (VGM-006 / Constitution V1
        # forbidden_shortcuts): protected_low/high := last confirmed opposing
        # pivot. This is the recency heuristic the doctrine forbids. We keep it
        # as the fallback when the causal algorithm abstains or is disabled.
        if brk.direction == Direction.BULLISH:
            legacy_protected = track.last_confirmed_low
        else:
            legacy_protected = track.last_confirmed_high

        chosen_protected: Optional[SwingObject] = legacy_protected
        protected_point_selection: Optional[Mapping[str, Any]] = None

        # WP-SMC-10/2: causal protected-point selection. When the flag is on,
        # run the §5 causal-necessity algorithm (smc_desk.structure.protected_point)
        # against the just-confirmed break. If it does NOT abstain AND its selected
        # candidate maps to an actual SwingObject in the pool, override the legacy
        # recency assignment with the causally-correct swing. Otherwise fall back to
        # the legacy assignment. The full ProtectedPointSelection (selected,
        # runner_up, abstained, rationale, graph_relationships) is ALWAYS recorded
        # in brk.metadata['protected_point_selection'] for audit -- even when we
        # fall back. Fail-safe: any error -> legacy assignment + no metadata.
        if causal_protected_point_enabled():
            try:
                protected_point_selection = _run_causal_protected_point_selection(
                    brk=brk,
                    swings=swings,
                    candles=candles,
                    current_time=current_time,
                )
                if protected_point_selection is not None and not protected_point_selection.get("abstained"):
                    chosen = protected_point_selection.get("selected") or {}
                    matched = _match_candidate_to_swing(
                        chosen, swings, brk.direction,
                        scope=str(getattr(brk, "structure_scope", "external") or "external"),
                        timeframe=brk.timeframe,
                    )
                    if matched is not None:
                        chosen_protected = matched
                        protected_point_selection = {
                            **protected_point_selection,
                            "applied_override": True,
                            "matched_swing_id": matched.object_id,
                            "matched_scope": _scope_for_swing(matched),
                            "matched_timeframe": matched.timeframe,
                        }
                    else:
                        protected_point_selection = {
                            **protected_point_selection,
                            "applied_override": False,
                            "fallback_reason": "causal_pick_not_a_registered_swing",
                        }
            except Exception as exc:  # noqa: BLE001 -- hot path; must never break detection
                protected_point_selection = {
                    "abstained": True,
                    "applied_override": False,
                    "fallback_reason": f"causal_selection_error:{type(exc).__name__}",
                    "rationale": str(exc)[:200],
                }

        if protected_point_selection is not None:
            brk.metadata["protected_point_selection"] = protected_point_selection

        if brk.direction == Direction.BULLISH:
            track.protected_low = chosen_protected
            track.last_bos_swing_id = chosen_protected.object_id if chosen_protected else None
            if track.active_high and track.active_high.object_id == broken_swing.object_id:
                track.active_high = None
        else:
            track.protected_high = chosen_protected
            track.last_bos_swing_id = chosen_protected.object_id if chosen_protected else None
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


def _run_causal_protected_point_selection(
    *,
    brk: StructureBreakObject,
    swings: List[SwingObject],
    candles: Sequence[Candle],
    current_time: datetime,
) -> Optional[Mapping[str, Any]]:
    """Adapt the confirmed break + swings + candles to the protected_point.select
    schema and return its ProtectedPointSelection as a JSON-serialisable mapping.

    This is the WP-SMC-10/2 wire: the causal-necessity algorithm
    (smc_desk.structure.protected_point.select) runs against the just-confirmed
    break. Returns None if the algorithm produces no candidates (so the caller
    falls back to the legacy recency assignment).
    """
    from smc_desk.structure.protected_point import select as pp_select

    direction = str(getattr(brk.direction, "value", brk.direction)).lower()
    required_pivot_type = "low" if direction == "bullish" else "high"

    # Adapter: SwingObject -> programme_schema mapping the algorithm reads.
    #
    # WP-SMC-11 (audit F1): the pool is SCOPE-LOCKED. Previously every swing
    # scale was flattened into one pool with structure scope discarded, so a
    # local or internal pivot could be selected as an external break's
    # protected point purely because it sat at a similar price -- 34 such
    # substitutions on 1,500 BTCUSDT candles, 19 on SOLUSDT. Doctrine is
    # explicit that local structure may refine an origin but never replace it,
    # so an external break may only consider external candidates on its own
    # owning timeframe.
    break_scope = str(getattr(brk, "structure_scope", "external") or "external")
    pool: list[Mapping[str, Any]] = []
    for s in swings:
        if _scope_for_swing(s) != break_scope:
            continue
        if s.timeframe != brk.timeframe:
            continue
        is_high = getattr(s.direction, "value", s.direction) == "BEARISH" or s.direction == Direction.BEARISH
        pivot_type = "high" if is_high else "low"
        pool.append({
            "object_id": s.object_id,
            "timeframe": s.timeframe,
            "structure_scope": _scope_for_swing(s),
            "pivot_type": pivot_type,
            "pivot_price": float(s.price_high if is_high else s.price_low),
            "price_low": float(s.price_low),
            "price_high": float(s.price_high),
            "lifecycle": "STRUCTURAL",
            "pivot_time": s.pivot_time.isoformat() if s.pivot_time else "",
            "confirmed_at": (s.confirmed_at.isoformat() if s.confirmed_at else None),
        })
    if not pool:
        return None

    accepted_break = {
        "object_id": brk.object_id,
        "timeframe": brk.timeframe,
        "direction": direction,
        "confirming_candle_time": brk.confirmed_at.isoformat() if brk.confirmed_at else "",
        # impulse/cluster ids are not carried by StructureBreakObject on the
        # canonical path; the algorithm degrades to its candidate-1 (opposing
        # structural pivot) which is still a causal improvement over recency.
        "impulse_candle_ids": [],
        "origin_cluster_candle_ids": list(brk.metadata.get("origin_cluster_candle_ids") or []),
    }

    candle_mappings = [
        {"timestamp": c.close_time.isoformat(), "close": float(c.close)}
        for c in candles
    ]

    selection = pp_select(
        accepted_break=accepted_break,
        candidate_pool=pool,
        active_range=None,
        timeframe_candles=candle_mappings,
        decision_time=current_time.isoformat() if current_time else None,
    )
    return _protected_point_selection_to_mapping(selection)


def _protected_point_selection_to_mapping(selection: Any) -> Optional[Mapping[str, Any]]:
    """Normalise a ProtectedPointSelection dataclass into a JSON-serialisable mapping."""
    if selection is None:
        return None

    def _cand(c: Any) -> dict[str, Any]:
        if c is None:
            return {}
        try:
            return c.to_dict()
        except AttributeError:
            return dict(c)

    return {
        "schema": getattr(selection, "schema", "protected_point_selection_v1"),
        "abstained": bool(getattr(selection, "abstained", True)),
        "rationale": str(getattr(selection, "rationale", "") or ""),
        "selected": _cand(getattr(selection, "selected", None)),
        "runner_up": _cand(getattr(selection, "runner_up", None)),
        "graph_relationships": list(getattr(selection, "graph_relationships", ()) or ()),
    }


def _match_candidate_to_swing(
    candidate: Mapping[str, Any],
    swings: List[SwingObject],
    direction: Direction,
    *,
    scope: str = "external",
    timeframe: str | None = None,
) -> Optional[SwingObject]:
    """Resolve a protected-point candidate back to its registered SwingObject.

    WP-SMC-11 (audit F1). Identity first, geometry second:

    1. Match on the candidate's own evidence id. The causal algorithm suffixes
       ids (``<swing_id>#internal``), so the base id is recovered and looked up
       directly. This is the only path that can establish identity.
    2. Only if no id is carried -- e.g. a cluster origin that is not a swing at
       all -- fall back to price, and then only within the same structure scope
       and timeframe.

    The previous implementation matched on price within 5bps and direction
    alone. Equal or nearby prices are common across scales, so a local pivot
    could silently become an external protected point. Doctrine forbids that:
    equal prices never make two swing ids interchangeable.
    """
    is_bullish = getattr(direction, "value", direction) == "BULLISH" or direction == Direction.BULLISH

    def _protects(swing: SwingObject) -> bool:
        """A bullish break protects a LOW; a bearish break protects a HIGH."""
        is_high = (
            getattr(swing.direction, "value", swing.direction) == "BEARISH"
            or swing.direction == Direction.BEARISH
        )
        return is_high != is_bullish

    eligible = [
        s for s in swings
        if _scope_for_swing(s) == scope
        and (timeframe is None or s.timeframe == timeframe)
        and _protects(s)
    ]

    # 1. Identity. Scope, timeframe and side are all pre-filtered above, so a
    # candidate naming a swing on the wrong side of the market resolves to
    # nothing rather than being adopted on the strength of its id alone.
    raw_id = str(candidate.get("internal_pivot_id") or candidate.get("candidate_id") or "")
    base_id = raw_id.split("#", 1)[0] if raw_id else ""
    if base_id:
        for s in eligible:
            if s.object_id == base_id:
                return s
        # An id was carried but names nothing eligible: refuse rather than
        # silently sliding to a same-priced neighbour.
        return None

    # 2. Geometry, scope-bounded, for non-swing origins only.
    price = candidate.get("pivot_price") or candidate.get("extreme_price")
    if price is None:
        return None
    try:
        price_f = float(price)
    except (TypeError, ValueError):
        return None
    if price_f <= 0:
        return None
    tol = max(price_f * 5e-4, 1e-9)
    best: Optional[SwingObject] = None
    best_dist = float("inf")
    for s in eligible:
        is_high = getattr(s.direction, "value", s.direction) == "BEARISH" or s.direction == Direction.BEARISH
        swing_price = float(s.price_high) if is_high else float(s.price_low)
        dist = abs(swing_price - price_f)
        if dist <= tol and dist < best_dist:
            best = s
            best_dist = dist
    return best
