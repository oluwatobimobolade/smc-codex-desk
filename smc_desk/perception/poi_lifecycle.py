"""Real POI lifecycle primitives for SMC watch states."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True)
class POIObject:
    poi_id: str
    kind: str
    timeframe: str
    direction: str
    price_low: Decimal
    price_high: Decimal
    origin_event_id: str | None
    created_by: str
    freshness: str
    price_relation: str
    event_history: list[dict[str, Any]]
    quality_score: float
    quality_reasons: list[str]
    current_price: Decimal | None
    validity_status: str
    scope: str
    rejection_reason: str | None
    protected_high: Decimal | None
    protected_low: Decimal | None
    active_range_high: Decimal | None
    active_range_low: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "poi_id": self.poi_id,
            "kind": self.kind,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "price_low": str(self.price_low),
            "price_high": str(self.price_high),
            "origin_event_id": self.origin_event_id,
            "created_by": self.created_by,
            "freshness": self.freshness,
            "price_relation": self.price_relation,
            "event_history": self.event_history,
            "quality_score": self.quality_score,
            "quality_reasons": self.quality_reasons,
            "current_price": None if self.current_price is None else str(self.current_price),
            "validity_status": self.validity_status,
            "scope": self.scope,
            "rejection_reason": self.rejection_reason,
            "protected_high": None if self.protected_high is None else str(self.protected_high),
            "protected_low": None if self.protected_low is None else str(self.protected_low),
            "active_range_high": None if self.active_range_high is None else str(self.active_range_high),
            "active_range_low": None if self.active_range_low is None else str(self.active_range_low),
        }


def build_poi_lifecycle_by_timeframe(
    perception_by_tf: Mapping[str, Mapping[str, Any]],
    hierarchy_by_tf: Mapping[str, Mapping[str, Any]],
    *,
    current_prices: Mapping[str, Decimal | str | float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    prices = current_prices or {}
    return {
        timeframe: [poi.to_dict() for poi in build_pois_for_timeframe(
            timeframe=timeframe,
            snapshot=perception_by_tf.get(timeframe, {}),
            hierarchy=hierarchy_by_tf.get(timeframe, {}),
            current_price=prices.get(timeframe),
        )]
        for timeframe in perception_by_tf
    }


def build_pois_for_timeframe(
    *,
    timeframe: str,
    snapshot: Mapping[str, Any],
    hierarchy: Mapping[str, Any],
    current_price: Decimal | str | float | None,
) -> list[POIObject]:
    price = Decimal(str(current_price)) if current_price is not None else _infer_price(snapshot)
    pois: list[POIObject] = []
    bias = str(hierarchy.get("external_bias", "neutral"))
    scope_context = _scope_context(hierarchy)
    for ob in snapshot.get("order_blocks", []) or []:
        direction = str(ob.get("direction", ""))
        if direction != bias:
            continue
        low = Decimal(str(ob["price_low"]))
        high = Decimal(str(ob["price_high"]))
        low, high = min(low, high), max(low, high)
        event_history = _event_history(ob)
        quality_score, quality_reasons = _quality_score(
            obj=ob, price=price, low=low, high=high, direction=direction, event_history=event_history
        )
        validity = classify_poi_scope(
            {
                "kind": "supply" if direction == "bearish" else "demand",
                "direction": direction,
                "price_low": low,
                "price_high": high,
            },
            external_bias=bias,
            protected_high=scope_context["protected_high"],
            protected_low=scope_context["protected_low"],
            current_price=price,
            active_range_high=scope_context["active_range_high"],
            active_range_low=scope_context["active_range_low"],
        )
        pois.append(
            POIObject(
                poi_id=f"{timeframe}:order_block:{ob.get('object_id')}",
                kind="supply" if direction == "bearish" else "demand",
                timeframe=timeframe,
                direction=direction,
                price_low=low,
                price_high=high,
                origin_event_id=(ob.get("evidence") or {}).get("structure_break_id") or ob.get("object_id"),
                created_by="order_block",
                freshness=_freshness_from_price(price, low, high, direction),
                price_relation=_price_relation(price, low, high, direction),
                event_history=event_history,
                quality_score=quality_score,
                quality_reasons=quality_reasons,
                current_price=price,
                validity_status=validity["validity_status"],
                scope=validity["scope"],
                rejection_reason=validity["rejection_reason"],
                protected_high=validity["protected_high"],
                protected_low=validity["protected_low"],
                active_range_high=validity["active_range_high"],
                active_range_low=validity["active_range_low"],
            )
        )

    latest_break = _find_break(snapshot, hierarchy.get("latest_external_break_id"))
    if latest_break and bias in {"bullish", "bearish"} and not pois:
        kind = "demand" if bias == "bullish" else "supply"
        low, high = _poi_zone_from_displacement_break(latest_break, bias)
        event_history = _event_history(latest_break)
        quality_score, quality_reasons = _quality_score(
            obj=latest_break, price=price, low=low, high=high, direction=bias, event_history=event_history
        )
        validity = classify_poi_scope(
            {
                "kind": kind,
                "direction": bias,
                "price_low": low,
                "price_high": high,
            },
            external_bias=bias,
            protected_high=scope_context["protected_high"],
            protected_low=scope_context["protected_low"],
            current_price=price,
            active_range_high=scope_context["active_range_high"],
            active_range_low=scope_context["active_range_low"],
        )
        pois.append(
            POIObject(
                poi_id=f"{timeframe}:{kind}:{latest_break.get('object_id')}",
                kind=kind,
                timeframe=timeframe,
                direction=bias,
                price_low=low,
                price_high=high,
                origin_event_id=latest_break.get("object_id"),
                created_by="displacement",
                freshness=_freshness_from_price(price, low, high, bias),
                price_relation=_price_relation(price, low, high, bias),
                event_history=event_history,
                quality_score=quality_score,
                quality_reasons=quality_reasons,
                current_price=price,
                validity_status=validity["validity_status"],
                scope=validity["scope"],
                rejection_reason=validity["rejection_reason"],
                protected_high=validity["protected_high"],
                protected_low=validity["protected_low"],
                active_range_high=validity["active_range_high"],
                active_range_low=validity["active_range_low"],
            )
        )
    for fvg in snapshot.get("fvgs", []) or []:
        direction = str(fvg.get("direction", ""))
        terminal = str(fvg.get("terminal_reason", "none"))
        evidence = fvg.get("evidence") or {}
        if evidence.get("poi_grade") is False:
            continue
        if direction != bias or terminal not in {"", "none"}:
            continue
        low = Decimal(str(fvg["price_low"]))
        high = Decimal(str(fvg["price_high"]))
        low, high = min(low, high), max(low, high)
        event_history = _event_history(fvg)
        quality_score, quality_reasons = _quality_score(
            obj=fvg, price=price, low=low, high=high, direction=direction, event_history=event_history
        )
        validity = classify_poi_scope(
            {
                "kind": "fvg",
                "direction": direction,
                "price_low": low,
                "price_high": high,
            },
            external_bias=bias,
            protected_high=scope_context["protected_high"],
            protected_low=scope_context["protected_low"],
            current_price=price,
            active_range_high=scope_context["active_range_high"],
            active_range_low=scope_context["active_range_low"],
        )
        pois.append(
            POIObject(
                poi_id=f"{timeframe}:fvg:{fvg.get('object_id')}",
                kind="fvg",
                timeframe=timeframe,
                direction=direction,
                price_low=low,
                price_high=high,
                origin_event_id=fvg.get("object_id"),
                created_by="fvg",
                freshness=str(fvg.get("mitigation_status", "fresh")),
                price_relation=_price_relation(price, low, high, direction),
                event_history=event_history,
                quality_score=quality_score,
                quality_reasons=quality_reasons,
                current_price=price,
                validity_status=validity["validity_status"],
                scope=validity["scope"],
                rejection_reason=validity["rejection_reason"],
                protected_high=validity["protected_high"],
                protected_low=validity["protected_low"],
                active_range_high=validity["active_range_high"],
                active_range_low=validity["active_range_low"],
            )
        )
    return pois


def classify_poi_scope(
    poi: Mapping[str, Any],
    *,
    external_bias: str,
    protected_high: Decimal | str | float | None,
    protected_low: Decimal | str | float | None,
    current_price: Decimal | str | float | None,
    active_range_high: Decimal | str | float | None,
    active_range_low: Decimal | str | float | None,
) -> dict[str, Any]:
    """Classify whether a POI can be the active setup POI.

    A valid active POI must live inside the currently protected external range.
    A beautiful higher-timeframe zone above the bearish protected high, or below
    the bullish protected low, is context only. It cannot drive the active setup.
    """
    direction = str(poi.get("direction") or "").lower()
    kind = str(poi.get("kind") or "").lower()
    low = _to_decimal(poi.get("price_low"))
    high = _to_decimal(poi.get("price_high"))
    protected_hi = _to_decimal(protected_high)
    protected_lo = _to_decimal(protected_low)
    range_hi = _to_decimal(active_range_high)
    range_lo = _to_decimal(active_range_low)
    _ = _to_decimal(current_price)  # kept for the public contract and future diagnostics
    if low is not None and high is not None and low > high:
        low, high = high, low

    base = {
        "protected_high": protected_hi,
        "protected_low": protected_lo,
        "active_range_high": range_hi,
        "active_range_low": range_lo,
    }
    if direction not in {"bullish", "bearish"} or direction != str(external_bias):
        return {
            **base,
            "validity_status": "INVALID_DIRECTION_MISMATCH",
            "scope": "rejected",
            "rejection_reason": f"POI direction {direction or 'unknown'} does not match external bias {external_bias}.",
        }
    if low is None or high is None:
        return {
            **base,
            "validity_status": "INVALID_PRICE_BOUNDS",
            "scope": "rejected",
            "rejection_reason": "POI missing price_low or price_high.",
        }
    if protected_hi is None or protected_lo is None or range_hi is None or range_lo is None:
        return {
            **base,
            "validity_status": "REVIEW_REQUIRED_INCOMPLETE_PROTECTED_RANGE",
            "scope": "rejected",
            "rejection_reason": "Protected high/low or active range is unavailable, so active POI authority is not certified.",
        }

    if direction == "bearish":
        if kind not in {"supply", "order_block", "fvg", "breaker"}:
            return {
                **base,
                "validity_status": "INVALID_KIND_FOR_BEARISH_SETUP",
                "scope": "rejected",
                "rejection_reason": f"Bearish setup requires supply/order_block/fvg/breaker, got {kind or 'unknown'}.",
            }
        if low > protected_hi:
            return {
                **base,
                "validity_status": "PARENT_SCOPE_POI",
                "scope": "parent_scope",
                "rejection_reason": "Bearish POI sits above the protected high, so price would challenge the bearish setup before touching it.",
            }
        if low <= protected_hi < high:
            return {
                **base,
                "validity_status": "REVIEW_REQUIRED_STRADDLES_PROTECTED_LEVEL",
                "scope": "rejected",
                "rejection_reason": "Bearish POI straddles the protected high; human review required before active use.",
            }
        if high > protected_hi:
            return {
                **base,
                "validity_status": "INVALID_OUTSIDE_PROTECTED_RANGE",
                "scope": "rejected",
                "rejection_reason": "Bearish POI extends above the protected high.",
            }
        if high > range_hi or low < range_lo:
            return {
                **base,
                "validity_status": "INVALID_OUTSIDE_ACTIVE_RANGE",
                "scope": "rejected",
                "rejection_reason": "Bearish POI is not contained inside the active dealing range.",
            }
        return {
            **base,
            "validity_status": "VALID_ACTIVE_SETUP_POI",
            "scope": "active_setup",
            "rejection_reason": None,
        }

    if kind not in {"demand", "order_block", "fvg", "breaker"}:
        return {
            **base,
            "validity_status": "INVALID_KIND_FOR_BULLISH_SETUP",
            "scope": "rejected",
            "rejection_reason": f"Bullish setup requires demand/order_block/fvg/breaker, got {kind or 'unknown'}.",
        }
    if high < protected_lo:
        return {
            **base,
            "validity_status": "PARENT_SCOPE_POI",
            "scope": "parent_scope",
            "rejection_reason": "Bullish POI sits below the protected low, so price would challenge the bullish setup before touching it.",
        }
    if low < protected_lo <= high:
        return {
            **base,
            "validity_status": "REVIEW_REQUIRED_STRADDLES_PROTECTED_LEVEL",
            "scope": "rejected",
            "rejection_reason": "Bullish POI straddles the protected low; human review required before active use.",
        }
    if low < protected_lo:
        return {
            **base,
            "validity_status": "INVALID_OUTSIDE_PROTECTED_RANGE",
            "scope": "rejected",
            "rejection_reason": "Bullish POI extends below the protected low.",
        }
    if high > range_hi or low < range_lo:
        return {
            **base,
            "validity_status": "INVALID_OUTSIDE_ACTIVE_RANGE",
            "scope": "rejected",
            "rejection_reason": "Bullish POI is not contained inside the active dealing range.",
        }
    return {
        **base,
        "validity_status": "VALID_ACTIVE_SETUP_POI",
        "scope": "active_setup",
        "rejection_reason": None,
    }


def build_poi_selection(pois_by_tf: Mapping[str, list[Mapping[str, Any]]], *, direction: str) -> dict[str, Any]:
    """Return a complete active-POI selection report."""
    all_candidates = _dedupe_candidates(pois_by_tf, direction=direction)
    ranked = _rank_candidates(all_candidates, direction=direction)
    current_range = [p for p in ranked if p.get("scope") == "active_setup" and p.get("validity_status") == "VALID_ACTIVE_SETUP_POI"]
    parent_scope = [p for p in ranked if p.get("scope") == "parent_scope"]
    rejected = [p for p in ranked if p.get("scope") not in {"active_setup", "parent_scope", "historical"}]
    historical = [p for p in ranked if p.get("scope") == "historical"]
    selected = current_range[0] if current_range else None
    status = "SELECTED_ACTIVE_POI" if selected else "NO_VALID_ACTIVE_POI_IN_CURRENT_1H_RANGE"
    if selected is None and rejected:
        if any(str(p.get("validity_status", "")).startswith("REVIEW_REQUIRED") for p in rejected):
            status = "REVIEW_REQUIRED_POI_OUTSIDE_PROTECTED_RANGE"
    if selected is None and parent_scope:
        status = "WATCH_NEW_LOWER_SUPPLY_FORMATION" if direction == "bearish" else "WATCH_NEW_HIGHER_DEMAND_FORMATION"
    return {
        "method": "ranked_active_poi_v2_protected_range_first",
        "status": status,
        "selected_active_poi": selected,
        "selected_poi_id": None if selected is None else selected.get("poi_id"),
        "candidate_count": len(all_candidates),
        "current_range_pois": current_range,
        "parent_scope_pois": parent_scope,
        "historical_pois": historical,
        "rejected_pois": rejected,
    }


def rank_poi_candidates(pois_by_tf: Mapping[str, list[Mapping[str, Any]]], *, direction: str) -> list[dict[str, Any]]:
    """Rank active POIs with a trader-readable score and reasons.

    The selector prefers the 1h setup POI when it is valid, but it no longer
    blindly takes the first matching object. Freshness, quality, relation to
    price, and distance all participate in the choice.
    """
    selection = build_poi_selection(pois_by_tf, direction=direction)
    return list(selection["current_range_pois"])


def select_active_poi(pois_by_tf: Mapping[str, list[Mapping[str, Any]]], *, direction: str) -> Mapping[str, Any] | None:
    return build_poi_selection(pois_by_tf, direction=direction).get("selected_active_poi")


def _dedupe_candidates(pois_by_tf: Mapping[str, list[Mapping[str, Any]]], *, direction: str) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for timeframe, pois in pois_by_tf.items():
        for raw in pois:
            if raw.get("direction") != direction:
                continue
            if raw.get("freshness") in {"invalidated", "full"}:
                continue
            poi = dict(raw)
            poi.setdefault("timeframe", timeframe)
            key = (
                str(poi.get("timeframe")),
                str(poi.get("kind")),
                str(poi.get("direction")),
                str(poi.get("price_low")),
                str(poi.get("price_high")),
                str(poi.get("origin_event_id") or poi.get("poi_id")),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(poi)
    return candidates


def _rank_candidates(candidates: list[dict[str, Any]], *, direction: str) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for poi in candidates:
        score, reasons, breakdown = _poi_rank_score(poi, timeframe=str(poi.get("timeframe", "")), direction=direction)
        poi["selection_score"] = round(score, 4)
        poi["selection_reasons"] = reasons
        poi["score_breakdown"] = {key: round(value, 4) for key, value in breakdown.items()}
        ranked.append(poi)
    ranked.sort(key=lambda poi: poi.get("selection_score", 0.0), reverse=True)
    for index, poi in enumerate(ranked, start=1):
        poi["selection_rank"] = index
    return ranked


def _poi_rank_score(poi: Mapping[str, Any], *, timeframe: str, direction: str) -> tuple[float, list[str], dict[str, float]]:
    reasons: list[str] = []
    score = 0.0
    breakdown: dict[str, float] = {}

    active_validity = 1.0 if poi.get("validity_status") == "VALID_ACTIVE_SETUP_POI" and poi.get("scope") == "active_setup" else -10.0
    score += active_validity
    breakdown["active_range_validity"] = active_validity
    if active_validity > 0:
        reasons.append("inside_active_protected_range")
    else:
        reasons.append(f"not_active_setup:{poi.get('validity_status')}")

    direction_alignment = 1.0 if poi.get("direction") == direction else -2.0
    score += direction_alignment
    breakdown["direction_alignment"] = direction_alignment

    timeframe_weight = {"1h": 0.34, "4h": 0.28, "1d": 0.20, "15m": 0.12}.get(timeframe, 0.05)
    score += timeframe_weight
    breakdown["timeframe_weight"] = timeframe_weight
    reasons.append(f"timeframe_weight:{timeframe}={timeframe_weight:.2f}")

    kind = str(poi.get("kind"))
    if kind in {"supply", "demand", "order_block"}:
        breakdown["poi_kind"] = 0.18
        score += breakdown["poi_kind"]
        reasons.append("institutional_zone_kind")
    elif kind == "fvg":
        breakdown["poi_kind"] = 0.08
        score += breakdown["poi_kind"]
        reasons.append("fvg_is_secondary_poi")
    else:
        breakdown["poi_kind"] = 0.0

    freshness = str(poi.get("freshness", "")).lower()
    freshness_weight = {"fresh": 0.18, "untouched": 0.18, "touched": 0.08, "partial": 0.06}.get(freshness, 0.02)
    score += freshness_weight
    breakdown["freshness"] = freshness_weight
    reasons.append(f"freshness:{freshness or 'unknown'}={freshness_weight:.2f}")

    relation = str(poi.get("price_relation", "")).lower()
    ideal_relation = "below_poi" if direction == "bearish" else "above_poi"
    if relation == ideal_relation:
        breakdown["price_relation"] = 0.16
        score += breakdown["price_relation"]
        reasons.append("price_waiting_for_retrace")
    elif relation == "inside_poi":
        breakdown["price_relation"] = 0.12
        score += breakdown["price_relation"]
        reasons.append("price_inside_poi_confirmation_required")
    elif relation.startswith("invalidated"):
        breakdown["price_relation"] = -1.0
        score += breakdown["price_relation"]
        reasons.append("invalidated_relation")
    else:
        breakdown["price_relation"] = 0.0

    quality = float(poi.get("quality_score", 0.0) or 0.0)
    quality_score = min(max(quality, 0.0), 1.0) * 0.22
    score += quality_score
    breakdown["displacement_origin"] = quality_score
    reasons.append(f"quality_score:{quality:.2f}")

    distance_score = _distance_score(poi)
    if distance_score is not None:
        score += distance_score
        breakdown["distance"] = distance_score
        reasons.append(f"distance_score:{distance_score:.2f}")
    else:
        breakdown["distance"] = 0.0

    breakdown.setdefault("premium_discount", 0.0)
    breakdown.setdefault("mitigation_status", 0.0)
    breakdown.setdefault("fvg_order_block_overlap", 0.0)
    breakdown.setdefault("inducement_liquidity_context", 0.0)
    return score, reasons, breakdown


def _scope_context(hierarchy: Mapping[str, Any]) -> dict[str, Decimal | None]:
    dr = hierarchy.get("dealing_range") or {}
    protected_high = _to_decimal(hierarchy.get("protected_high"))
    protected_low = _to_decimal(hierarchy.get("protected_low"))
    active_range_high = _to_decimal(dr.get("range_high") or hierarchy.get("external_range_high") or protected_high)
    active_range_low = _to_decimal(dr.get("range_low") or hierarchy.get("external_range_low") or protected_low)
    return {
        "protected_high": protected_high,
        "protected_low": protected_low,
        "active_range_high": active_range_high,
        "active_range_low": active_range_low,
    }


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _distance_score(poi: Mapping[str, Any]) -> float | None:
    try:
        current = Decimal(str(poi.get("current_price")))
        low = Decimal(str(poi["price_low"]))
        high = Decimal(str(poi["price_high"]))
    except Exception:
        return None
    if current <= 0:
        return None
    midpoint = (low + high) / Decimal("2")
    distance_pct = abs(midpoint - current) / current
    if distance_pct <= Decimal("0.005"):
        return 0.10
    if distance_pct <= Decimal("0.015"):
        return 0.07
    if distance_pct <= Decimal("0.03"):
        return 0.03
    return 0.0


def _event_history(obj: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return a stable, readable event timeline for the POI."""
    history = []
    for ev in obj.get("events", []) or []:
        history.append({
            "event_type": ev.get("event_type"),
            "timestamp": ev.get("timestamp"),
            "details": ev.get("details"),
        })
    mitigation = str(obj.get("mitigation_status", "")).lower()
    terminal = str(obj.get("terminal_reason", "none")).lower()
    if mitigation:
        history.append({"event_type": "CURRENT_MITIGATION", "value": mitigation})
    if terminal not in {"", "none"}:
        history.append({"event_type": "TERMINAL_REASON", "value": terminal})
    return history


def _quality_score(
    *,
    obj: Mapping[str, Any],
    price: Decimal,
    low: Decimal,
    high: Decimal,
    direction: str,
    event_history: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    """Compute a simple POI quality score and explanatory reasons."""
    reasons: list[str] = []
    score = float(obj.get("confidence", 0.0) or 0.0)
    mitigation = str(obj.get("mitigation_status", "")).lower()
    terminal = str(obj.get("terminal_reason", "none")).lower()
    if mitigation == "untouched":
        score += 0.25
        reasons.append("untouched")
    elif mitigation == "partial":
        score += 0.10
        reasons.append("partially_mitigated")
    if terminal in {"", "none"}:
        score += 0.15
        reasons.append("no_terminal_reason")
    if _price_relation(price, low, high, direction) == "fresh":
        score += 0.20
        reasons.append("price_not_yet_in_zone")
    if any(ev.get("event_type") == "OBJECT_CONFIRMED" for ev in event_history):
        score += 0.15
        reasons.append("confirmed")
    return min(score, 1.0), reasons


def _find_break(snapshot: Mapping[str, Any], object_id: str | None) -> Mapping[str, Any] | None:
    if not object_id:
        return None
    for brk in snapshot.get("structure_breaks", []) or []:
        if brk.get("object_id") == object_id:
            return brk
    return None


def _poi_zone_from_displacement_break(structure_break: Mapping[str, Any], direction: str) -> tuple[Decimal, Decimal]:
    """Extract the likely source POI from a displacement candle.

    A full impulse candle is usually too broad to be a useful supply/demand
    zone. Until the dedicated order-block detector lands, use the source-side
    quartile: upper quartile for bearish supply, lower quartile for bullish
    demand. This is intentionally conservative and labelled as displacement-
    created POI, not certified OB truth.
    """
    low = Decimal(str(structure_break["price_low"]))
    high = Decimal(str(structure_break["price_high"]))
    bottom, top = min(low, high), max(low, high)
    width = top - bottom
    if width <= 0:
        return bottom, top
    if direction == "bearish":
        return top - width * Decimal("0.25"), top
    if direction == "bullish":
        return bottom, bottom + width * Decimal("0.25")
    return bottom, top


def _infer_price(snapshot: Mapping[str, Any]) -> Decimal:
    breaks = snapshot.get("structure_breaks", []) or []
    if breaks:
        brk = breaks[-1]
        return (Decimal(str(brk["price_low"])) + Decimal(str(brk["price_high"]))) / Decimal("2")
    return Decimal("0")


def _price_relation(price: Decimal, low: Decimal, high: Decimal, direction: str) -> str:
    if low <= price <= high:
        return "inside_poi"
    if direction == "bearish":
        if price < low:
            return "below_poi"
        return "invalidated_above"
    if direction == "bullish":
        if price > high:
            return "above_poi"
        return "invalidated_below"
    return "outside_poi"


def _freshness_from_price(price: Decimal, low: Decimal, high: Decimal, direction: str) -> str:
    relation = _price_relation(price, low, high, direction)
    if relation.startswith("invalidated"):
        return "invalidated"
    if relation == "inside_poi":
        return "touched"
    return "fresh"
