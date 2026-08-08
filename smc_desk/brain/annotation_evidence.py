"""Canonical evidence anchors for professional SMC chart markup.

An annotation can be aesthetically sparse only after it is mechanically true.
This module translates detector and graph objects into the exact price/time
geometry a V2 drawing is allowed to use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class AnnotationEvidenceAnchor:
    object_id: str
    evidence_type: str
    timeframe: str
    direction: str | None
    structure_scope: str | None
    kind: str | None
    price_low: float | None
    price_high: float | None
    exact_price: float | None
    start_time: str | None
    end_time: str | None
    start_index: int | None
    end_index: int | None
    confirmation_status: str | None
    activity_status: str | None
    mitigation_status: str | None
    is_wick_only_probe: bool
    confidence: float | None
    source: str


def build_annotation_evidence_index(evidence_pack: Mapping[str, Any]) -> dict[str, AnnotationEvidenceAnchor]:
    """Return a stable object-id index with chart-ready geometry."""
    index: dict[str, AnnotationEvidenceAnchor] = {}
    detector_candidates = evidence_pack.get("detector_candidates") or {}
    if isinstance(detector_candidates, Mapping):
        for timeframe, payload in detector_candidates.items():
            if not isinstance(payload, Mapping):
                continue
            for bucket, items in payload.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    anchor = _candidate_anchor(str(timeframe), str(bucket), item, evidence_pack)
                    if anchor is not None:
                        index[anchor.object_id] = anchor

    graph = evidence_pack.get("formal_structure_graph") or {}
    active_range = graph.get("active_range") if isinstance(graph, Mapping) else None
    if isinstance(active_range, Mapping) and active_range.get("range_id"):
        object_id = str(active_range["range_id"])
        low = _float(active_range.get("low"))
        high = _float(active_range.get("high"))
        index[object_id] = AnnotationEvidenceAnchor(
            object_id=object_id,
            evidence_type="active_range",
            timeframe=str(active_range.get("timeframe") or "unknown"),
            direction=_enum_value(active_range.get("direction")),
            structure_scope="external",
            kind="active_range",
            price_low=low,
            price_high=high,
            exact_price=None,
            start_time=None,
            end_time=None,
            start_index=None,
            end_index=None,
            confirmation_status="confirmed",
            activity_status="active",
            mitigation_status="untouched",
            is_wick_only_probe=False,
            confidence=1.0,
            source="formal_structure_graph.active_range",
        )
    return index


def price_tolerance(price: float | None, *, basis_points: float = 8.0) -> float:
    return max(abs(float(price or 0.0)) * basis_points / 10_000.0, 1e-9)


def prices_match(actual: float | None, expected: float | None, *, basis_points: float = 8.0) -> bool:
    if actual is None or expected is None:
        return False
    return abs(float(actual) - float(expected)) <= price_tolerance(expected, basis_points=basis_points)


def zones_match(
    actual_low: float | None,
    actual_high: float | None,
    expected_low: float | None,
    expected_high: float | None,
    *,
    basis_points: float = 8.0,
) -> bool:
    if None in {actual_low, actual_high, expected_low, expected_high}:
        return False
    low, high = sorted((float(actual_low), float(actual_high)))
    expected_l, expected_h = sorted((float(expected_low), float(expected_high)))
    return prices_match(low, expected_l, basis_points=basis_points) and prices_match(high, expected_h, basis_points=basis_points)


def index_for_time(evidence_pack: Mapping[str, Any], timeframe: str, value: str | None) -> int | None:
    if not value:
        return None
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get(timeframe) if isinstance(windows, Mapping) else None
    if not isinstance(candles, list):
        return None
    target = _parse_time(value)
    if target is None:
        return None
    parsed_stamps: list[tuple[int, datetime]] = []
    for idx, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            continue
        stamp = _parse_time(str(candle.get("timestamp") or candle.get("open_time") or ""))
        if stamp is None:
            continue
        parsed_stamps.append((idx, stamp))
    if not parsed_stamps:
        return None
    first_stamp = min(stamp for _idx, stamp in parsed_stamps)
    last_stamp = max(stamp for _idx, stamp in parsed_stamps)
    if target < first_stamp or target > last_stamp:
        return None
    best: tuple[float, int] | None = None
    for idx, stamp in parsed_stamps:
        delta = abs((stamp - target).total_seconds())
        if best is None or delta < best[0]:
            best = (delta, idx)
    return None if best is None else best[1]


def observed_poi_state(anchor: AnnotationEvidenceAnchor, evidence_pack: Mapping[str, Any]) -> str:
    """Return fresh/partial/consumed/invalidated from candles after confirmation."""
    windows = evidence_pack.get("ohlcv_windows") or {}
    candles = windows.get(anchor.timeframe) if isinstance(windows, Mapping) else None
    if (
        not isinstance(candles, list)
        or anchor.end_index is None
        or anchor.price_low is None
        or anchor.price_high is None
    ):
        return "unverifiable"
    touched = False
    for raw in candles[anchor.end_index + 1 :]:
        if not isinstance(raw, Mapping):
            continue
        low = _float(raw.get("low"))
        high = _float(raw.get("high"))
        close = _float(raw.get("close"))
        if low is None or high is None or close is None:
            return "unverifiable"
        if anchor.direction == "bullish":
            if close < anchor.price_low:
                return "invalidated"
            if low <= anchor.price_low:
                return "consumed"
            touched = touched or low <= anchor.price_high
        elif anchor.direction == "bearish":
            if close > anchor.price_high:
                return "invalidated"
            if high >= anchor.price_high:
                return "consumed"
            touched = touched or high >= anchor.price_low
        else:
            return "unverifiable"
    return "partial" if touched else "fresh"


def _candidate_anchor(
    timeframe: str,
    bucket: str,
    item: Mapping[str, Any],
    evidence_pack: Mapping[str, Any],
) -> AnnotationEvidenceAnchor | None:
    raw_id = item.get("object_id") or item.get("id") or item.get("liquidity_id") or item.get("poi_id")
    if raw_id is None:
        return None
    object_id = str(raw_id)
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    evidence_type = _bucket_to_type(bucket, item)
    price_low = _float(item.get("price_low"))
    price_high = _float(item.get("price_high"))
    scalar_price = _float(item.get("price"))
    if price_low is None and scalar_price is not None:
        price_low = scalar_price
    if price_high is None and scalar_price is not None:
        price_high = scalar_price
    exact_price = _float(evidence.get("broken_price")) if evidence_type == "structure" else None
    if exact_price is None and price_low is not None and price_high is not None and price_low == price_high:
        exact_price = price_low
    pivot_time = _time_string(item.get("pivot_time"))
    candidate_at = _time_string(item.get("candidate_at"))
    confirmed_at = _time_string(item.get("confirmed_at"))
    start_time = pivot_time or candidate_at
    end_time = confirmed_at or candidate_at or pivot_time
    return AnnotationEvidenceAnchor(
        object_id=object_id,
        evidence_type=evidence_type,
        timeframe=str(item.get("timeframe") or timeframe),
        direction=_enum_value(item.get("direction")),
        structure_scope=str(item.get("structure_scope") or evidence.get("structure_scope") or "") or None,
        kind=str(item.get("break_type") or item.get("object_type") or bucket).lower(),
        price_low=price_low,
        price_high=price_high,
        exact_price=exact_price,
        start_time=start_time,
        end_time=end_time,
        start_index=index_for_time(evidence_pack, str(item.get("timeframe") or timeframe), start_time),
        end_index=index_for_time(evidence_pack, str(item.get("timeframe") or timeframe), end_time),
        confirmation_status=_enum_value(item.get("confirmation_status")),
        activity_status=_enum_value(item.get("activity_status")),
        mitigation_status=_enum_value(item.get("mitigation_status")),
        is_wick_only_probe=bool(evidence.get("is_unconfirmed_probe") or item.get("is_wick_only_probe")),
        confidence=_float(item.get("confidence")),
        source=f"detector_candidates.{timeframe}.{bucket}",
    )


def _bucket_to_type(bucket: str, item: Mapping[str, Any]) -> str:
    if bucket in {"structure_breaks", "breaks"}:
        return "structure"
    if bucket == "order_blocks":
        return "order_block"
    if bucket in {"fvgs", "poi_grade_fvgs"}:
        return "fvg"
    if bucket == "liquidity_levels":
        return "liquidity"
    return str(item.get("object_type") or bucket).lower()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value)).lower()


def _time_string(value: Any) -> str | None:
    if value is None:
        return None
    parsed = _parse_time(str(value))
    return parsed.isoformat().replace("+00:00", "Z") if parsed is not None else None


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
