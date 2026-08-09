"""Order-block and POI-grade FVG detection for PerceptionEngineV2."""
from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from smc_desk.data.schemas import Candle
from smc_desk.perception.causal_repair_flags import causal_ob_origin_gate_enabled
from smc_desk.perception.lifecycle import EventType, SMCEvent, apply_event
from smc_desk.perception.ontology import (
    ConfirmationStatus,
    Direction,
    FairValueGapObject,
    OrderBlockEvidence,
    OrderBlockObject,
    StructureBreakObject,
)


class OrderBlockDetector:
    def __init__(self, detector_version: str = "2.0", lookback: int = 8, min_body_ratio: float = 0.25):
        self.detector_version = detector_version
        self.lookback = lookback
        self.min_body_ratio = min_body_ratio
        self.configuration_hash = hashlib.sha256(b"order_block_v3_causal_origin_cluster").hexdigest()[:8]

    def detect(
        self,
        candles: List[Candle],
        structure_breaks: Iterable[StructureBreakObject],
        fvgs: Iterable[FairValueGapObject],
        current_time: datetime,
    ) -> list[OrderBlockObject]:
        by_open = {c.open_time: idx for idx, c in enumerate(candles)}
        fvg_list = list(fvgs)
        order_blocks: list[OrderBlockObject] = []
        # One move produces both an internal and an external break, and both
        # trace back to the same opposing base. The zone is the same zone; only
        # the strongest-scoped emission is kept.
        seen_clusters: dict[tuple, int] = {}
        for brk in structure_breaks:
            if not brk.confirmed_at or brk.confirmed_at > current_time:
                continue
            if brk.confirmation_status != ConfirmationStatus.CONFIRMED:
                continue
            break_index = by_open.get(brk.candidate_at)
            if break_index is None:
                break_index = _first_candle_at_or_after(candles, brk.candidate_at)
            if break_index is None:
                continue
            origin_cluster = self._find_origin_cluster(candles, break_index, brk.direction)
            if origin_cluster is None:
                continue
            cluster_start, cluster_end = origin_cluster
            cluster = candles[cluster_start : cluster_end + 1]
            source = cluster[-1]
            body_ratio = max((_body_ratio(candle) for candle in cluster), default=0.0)
            # Body size is a FACT about the candle, not a verdict on the order
            # block. Dropping thin-bodied clusters here destroyed information
            # nothing downstream could recover -- and it destroyed exactly the
            # ones that matter, because a turning-point candle is usually
            # small-bodied with a long rejection wick. On CADJPY 4H the last
            # bullish candle before a 1.9x ATR collapse that broke structure
            # had a 0.106 body ratio and was discarded against a 0.75 floor.
            #
            # The ratio is recorded on the evidence so ranking and AI review
            # can weigh it against displacement, structure causation, location
            # and freshness -- which is where that judgement belongs.
            below_body_floor = body_ratio < self.min_body_ratio
            cluster_ids = [_candle_id(candle) for candle in cluster]
            departure = candles[cluster_end + 1 : break_index + 1]
            departure_ids = [_candle_id(candle) for candle in departure]

            # WP-SMC-10/3: causal OB-origin gate. An order block IS the origin of
            # displacement -- the opposing base whose departure produced the
            # impulsive, structure-breaking move. When the flag is ON we admit a
            # cluster as an OB only when (a) the accepted break carries a real
            # displacement_score (populated by engine_v2._enrich_breaks_with_displacement)
            # of at least the "moderate" quality threshold, AND (b) the cluster's
            # departure overlap with the break's source candles holds (it does by
            # construction -- departure leads into the break). When the flag is OFF
            # the detector keeps its legacy geometric behaviour: nearest
            # opposing-color cluster, body-ratio gate only.
            admission = _admit_origin_cluster(brk, departure_ids)
            if admission["admitted"] is False:
                # Emitted, not discarded. A candidate the causal gate rejects is
                # still a real opposing base a trader may reference; dropping it
                # left downstream ranking and AI review with nothing to weigh
                # and no way to explain why one zone was preferred over another.
                # It carries poi_grade=False so it can never be mistaken for a
                # promoted POI.
                pass
            origin_fvg = _causal_origin_fvg(
                brk,
                fvg_list,
                origin_start=cluster[0].open_time,
                departure_ids=set(departure_ids),
            )
            evidence = OrderBlockEvidence(
                originating_fvg_id=None if origin_fvg is None else origin_fvg.object_id,
                volume_ratio=1.0,
                structure_break_id=brk.object_id,
                source_candle_id=_candle_id(source),
                body_ratio=body_ratio,
                # Facts, so selection can reason instead of guess.
                # Validation is causal, not cosmetic: the departure must have
                # produced displacement AND the move must have broken structure.
                # Body size stays a recorded fact and no longer decides this.
                poi_grade=bool(admission["admitted"]),
                caused_structure_break=True,
                below_body_floor=below_body_floor,
                admission_status=str(admission.get("reason") or ("admitted" if admission["admitted"] else "rejected")),
            )
            break_identity = hashlib.sha256(str(brk.object_id).encode("utf-8")).hexdigest()[:10]
            obj = OrderBlockObject(
                object_id=(
                    f"ob_{brk.direction.value if hasattr(brk.direction, 'value') else brk.direction}_"
                    f"{cluster[0].open_time.timestamp()}_{cluster[-1].open_time.timestamp()}_"
                    f"break_{break_identity}"
                ),
                venue=source.venue,
                instrument=source.instrument,
                timeframe=source.timeframe,
                pivot_time=cluster[0].open_time,
                candidate_at=brk.candidate_at,
                confirmed_at=brk.confirmed_at,
                current_as_of=current_time,
                schema_version="1.0.0",
                detector_version=self.detector_version,
                configuration_hash=self.configuration_hash,
                source_candle_ids=[*cluster_ids, *departure_ids],
                last_updated_at=current_time,
                confidence=min(0.92, 0.58 + body_ratio * 0.34 + (0.08 if origin_fvg else 0.0)),
                direction=brk.direction,
                price_low=min(candle.low for candle in cluster),
                price_high=max(candle.high for candle in cluster),
                evidence=evidence,
                confirmation_status=ConfirmationStatus.CONFIRMED,
                metadata={
                    "candidate_authority": "causal_candidate_not_final_poi",
                    "causal_link_method": "explicit_break_departure_trace",
                    "linked_break_id": brk.object_id,
                    "origin_geometry": "single_candle" if len(cluster) == 1 else "multi_candle_cluster",
                    "origin_cluster_start_id": cluster_ids[0],
                    "origin_cluster_end_id": cluster_ids[-1],
                    "origin_cluster_candle_ids": cluster_ids,
                    "departure_candle_ids": departure_ids,
                    "originating_fvg_link_method": (
                        "causal_impulse_overlap" if origin_fvg is not None else None
                    ),
                    "causal_origin_admission": admission,
                },
            )
            zone_key = (
                str(getattr(brk.direction, "value", brk.direction)),
                str(obj.price_low), str(obj.price_high), cluster_ids[0], cluster_ids[-1],
            )
            existing_index = seen_clusters.get(zone_key)
            if existing_index is not None:
                existing = order_blocks[existing_index]
                keep_new = (
                    bool(evidence.poi_grade) and not bool(existing.evidence.poi_grade)
                ) or (
                    str(brk.structure_scope) == "external"
                    and str(existing.metadata.get("linked_break_scope")) != "external"
                )
                if not keep_new:
                    continue
                order_blocks.pop(existing_index)
                seen_clusters = {
                    key: (idx - 1 if idx > existing_index else idx)
                    for key, idx in seen_clusters.items()
                    if key != zone_key
                }
            obj.metadata["linked_break_scope"] = str(brk.structure_scope)
            seen_clusters[zone_key] = len(order_blocks)

            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CREATED,
                    timestamp=cluster[0].open_time,
                    trigger_candle_id=cluster_ids[0],
                    details="Causal order-block origin cluster candidate created",
                ),
            )
            apply_event(
                obj,
                SMCEvent(
                    event_type=EventType.OBJECT_CONFIRMED,
                    timestamp=brk.confirmed_at,
                    trigger_candle_id=_candle_id(candles[break_index]),
                    details="Origin cluster explicitly linked to the accepted structure-breaking departure",
                ),
            )
            order_blocks.append(obj)
        return order_blocks

    def _find_origin_cluster(
        self, candles: List[Candle], break_index: int, direction: Direction,
    ) -> Optional[tuple[int, int]]:
        """Return the contiguous opposing base nearest the causal departure.

        This remains candidate generation. Final POI authority is decided later,
        but the detector must preserve the full base instead of pretending the
        first opposite-coloured candle is always the complete origin.
        """
        direction_value = getattr(direction, "value", direction)
        start = max(0, break_index - self.lookback)
        source_index: int | None = None
        for idx in range(break_index - 1, start - 1, -1):
            candle = candles[idx]
            if _is_opposing(candle, direction_value):
                source_index = idx
                break
        if source_index is None:
            return None

        cluster_start = source_index
        while cluster_start > start and _is_opposing(candles[cluster_start - 1], direction_value):
            cluster_start -= 1
        return cluster_start, source_index


# WP-SMC-10/3 thresholds. A cluster is admitted as a causal OB origin when the
# accepted break's displacement quality is at least "moderate" per
# smc_desk.perception.displacement.score_break_displacement (score >= 0.45 and
# close_beyond_structure_bps >= 4.0). Below that the departure did not produce
# real displacement, so the cluster is a geometric base, not a causal origin.
_ORIGIN_DISPLACEMENT_MIN_SCORE = 0.45
_ORIGIN_DISPLACEMENT_MIN_BPS = 4.0


def _admit_origin_cluster(brk: StructureBreakObject, departure_ids: list[str]) -> dict:
    """Decide whether an origin cluster is admitted as a causal order block.

    When the origin gate flag is OFF, every geometric candidate is admitted
    (legacy behaviour) and the admission record tags itself ``gate_disabled``.

    When the flag is ON, the cluster is admitted only when the linked break
    carries a real displacement profile (metadata['displacement'] populated by
    engine_v2._enrich_breaks_with_displacement when the displacement-scoring flag
    is also on) meeting the moderate-quality threshold AND the departure is
    non-empty (a real departure must exist between the cluster and the break).

    Returns a JSON-serialisable admission record attached to the OB's metadata.
    """
    if not causal_ob_origin_gate_enabled():
        return {
            "admitted": True,
            "gate": "disabled",
            "reason": "causal_ob_origin_gate_off_legacy_geometric_admission",
        }

    disp = brk.metadata.get("displacement") if isinstance(brk.metadata, dict) else None
    if not isinstance(disp, dict):
        return {
            "admitted": False,
            "gate": "enabled",
            "reason": "no_displacement_profile_on_break",
            "hint": "requires SMC_CANONICAL_DISPLACEMENT_SCORING=1 on the engine path",
        }
    score = float(disp.get("score") or 0.0)
    bps = float(disp.get("close_beyond_structure_bps") or 0.0)
    quality = str(disp.get("break_quality") or "weak")
    if not departure_ids:
        return {
            "admitted": False,
            "gate": "enabled",
            "reason": "no_departure_trace",
            "score": score,
            "close_beyond_structure_bps": bps,
            "break_quality": quality,
        }
    if score < _ORIGIN_DISPLACEMENT_MIN_SCORE or bps < _ORIGIN_DISPLACEMENT_MIN_BPS:
        return {
            "admitted": False,
            "gate": "enabled",
            "reason": "departure_lacks_displacement",
            "score": score,
            "close_beyond_structure_bps": bps,
            "break_quality": quality,
            "thresholds": {
                "min_score": _ORIGIN_DISPLACEMENT_MIN_SCORE,
                "min_bps": _ORIGIN_DISPLACEMENT_MIN_BPS,
            },
        }
    return {
        "admitted": True,
        "gate": "enabled",
        "reason": "departure_produced_displacement_into_accepted_break",
        "score": score,
        "close_beyond_structure_bps": bps,
        "break_quality": quality,
    }


def mark_poi_grade_fvgs(
    fvgs: Iterable[FairValueGapObject],
    structure_breaks: Iterable[StructureBreakObject],
    *,
    max_seconds: int = 8 * 60 * 60,
) -> list[FairValueGapObject]:
    """Mark FVGs only when their source candles overlap the accepted break impulse.

    ``max_seconds`` remains for call compatibility and bounds stale associations;
    proximity alone is never enough.
    """
    fvg_list = list(fvgs)
    confirmed_breaks = [b for b in structure_breaks if b.confirmed_at and b.confirmation_status == ConfirmationStatus.CONFIRMED]
    for fvg in fvg_list:
        fvg.evidence.poi_grade = False
        fvg.evidence.origin_break_id = None
        fvg.evidence.location_context = None
        for brk in confirmed_breaks:
            if _direction(brk.direction) != _direction(fvg.direction):
                continue
            if fvg.confirmed_at is None or brk.confirmed_at is None:
                continue
            delta = (brk.confirmed_at - fvg.confirmed_at).total_seconds()
            if delta < 0 or delta > max_seconds:
                continue
            if not set(fvg.source_candle_ids).intersection(brk.source_candle_ids):
                continue
            fvg.evidence.poi_grade = True
            fvg.evidence.origin_break_id = brk.object_id
            fvg.evidence.location_context = "causal_impulse_overlap"
            fvg.metadata["causal_link_method"] = "break_source_candle_overlap"
            fvg.metadata["linked_break_id"] = brk.object_id
            break
    return fvg_list


def _causal_origin_fvg(
    brk: StructureBreakObject,
    fvgs: list[FairValueGapObject],
    *,
    origin_start: datetime,
    departure_ids: set[str],
) -> FairValueGapObject | None:
    candidates = []
    for fvg in fvgs:
        if not fvg.confirmed_at or not brk.confirmed_at:
            continue
        if _direction(fvg.direction) != _direction(brk.direction):
            continue
        if fvg.confirmed_at < origin_start or fvg.confirmed_at > brk.confirmed_at:
            continue
        if not set(fvg.source_candle_ids).intersection(departure_ids):
            continue
        delta = (brk.confirmed_at - fvg.confirmed_at).total_seconds()
        candidates.append((delta, fvg))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _first_candle_at_or_after(candles: list[Candle], when: datetime) -> int | None:
    for idx, candle in enumerate(candles):
        if candle.open_time >= when:
            return idx
    return None


def _body_ratio(candle: Candle) -> float:
    rng = candle.high - candle.low
    if rng <= 0:
        return 0.0
    return float(abs(candle.close - candle.open) / rng)


def _direction(value: object) -> str:
    return str(getattr(value, "value", value)).lower()


def _is_opposing(candle: Candle, direction: object) -> bool:
    direction_value = str(getattr(direction, "value", direction)).lower()
    return (
        direction_value == "bullish" and candle.close < candle.open
    ) or (
        direction_value == "bearish" and candle.close > candle.open
    )


def _candle_id(candle: Candle) -> str:
    return f"c_{candle.open_time.timestamp()}"
