"""Break displacement and quality scoring.

This module does not decide trade direction. It turns a raw BOS/CHoCH object
into evidence a higher-level SMC interpretation layer can use. Weak opposite
breaks are allowed to exist as detector events, but they should not flip
external bias by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DisplacementProfile:
    body_to_range_ratio: float
    body_to_atr_ratio: float
    close_beyond_structure_bps: float
    fvg_created_after_break: bool
    impulse_candle_count: int
    wick_rejection_ratio: float
    displacement_score: float
    break_quality: str
    valid_for_bias_flip: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_to_range_ratio": round(self.body_to_range_ratio, 4),
            "body_to_atr_ratio": round(self.body_to_atr_ratio, 4),
            "close_beyond_structure_bps": round(self.close_beyond_structure_bps, 4),
            "fvg_created_after_break": self.fvg_created_after_break,
            "impulse_candle_count": self.impulse_candle_count,
            "wick_rejection_ratio": round(self.wick_rejection_ratio, 4),
            "displacement_score": round(self.displacement_score, 4),
            "break_quality": self.break_quality,
            "valid_for_bias_flip": self.valid_for_bias_flip,
        }


def score_break_displacement(
    structure_break: Any,
    *,
    fvgs: Sequence[Any] | None = None,
    atr: float | Decimal | None = None,
) -> DisplacementProfile:
    """Score whether a raw structure break has real displacement quality."""
    payload = _as_mapping(structure_break)
    evidence = _as_mapping(payload.get("evidence", {}))
    direction = str(payload.get("direction", "")).lower()

    body_to_range_ratio = abs(_float(evidence.get("candle_body_ratio"), 0.0))
    body_close_pen = max(_float(evidence.get("body_close_penetration"), 0.0), 0.0)
    broken_price = max(_float(evidence.get("broken_price"), 0.0), 1e-9)
    close_beyond_structure_bps = body_close_pen / broken_price * 10_000

    price_low = _float(payload.get("price_low"), 0.0)
    price_high = _float(payload.get("price_high"), 0.0)
    candle_range = max(price_high - price_low, 1e-9)
    body_to_atr_ratio = body_close_pen / max(_float(atr, candle_range), 1e-9)

    wick_pen = max(_float(evidence.get("wick_penetration"), 0.0), 0.0)
    wick_rejection_ratio = max(wick_pen - body_close_pen, 0.0) / max(wick_pen, 1e-9)
    fvg_created_after_break = _has_nearby_fvg(payload, direction, fvgs or [])

    impulse_candle_count = int(evidence.get("impulse_candle_count") or 1)
    body_component = min(body_to_range_ratio / 0.70, 1.0)
    close_component = min(close_beyond_structure_bps / 25.0, 1.0)
    atr_component = min(body_to_atr_ratio / 0.75, 1.0)
    fvg_component = 1.0 if fvg_created_after_break else 0.0
    rejection_penalty = min(wick_rejection_ratio * 0.20, 0.20)

    score = (
        body_component * 0.35
        + close_component * 0.35
        + atr_component * 0.20
        + fvg_component * 0.10
        - rejection_penalty
    )
    score = max(0.0, min(score, 1.0))
    if score >= 0.75 and body_to_range_ratio >= 0.55 and close_beyond_structure_bps >= 12.0:
        quality = "strong"
    elif score >= 0.45 and close_beyond_structure_bps >= 4.0:
        quality = "moderate"
    else:
        quality = "weak"

    return DisplacementProfile(
        body_to_range_ratio=body_to_range_ratio,
        body_to_atr_ratio=body_to_atr_ratio,
        close_beyond_structure_bps=close_beyond_structure_bps,
        fvg_created_after_break=fvg_created_after_break,
        impulse_candle_count=impulse_candle_count,
        wick_rejection_ratio=wick_rejection_ratio,
        displacement_score=score,
        break_quality=quality,
        valid_for_bias_flip=quality == "strong",
    )


def _has_nearby_fvg(structure_break: Mapping[str, Any], direction: str, fvgs: Sequence[Any]) -> bool:
    confirmed_at = _parse_dt(structure_break.get("confirmed_at") or structure_break.get("candidate_at"))
    for raw in fvgs:
        fvg = _as_mapping(raw)
        if str(fvg.get("direction", "")).lower() != direction:
            continue
        fvg_time = _parse_dt(fvg.get("confirmed_at") or fvg.get("candidate_at"))
        if confirmed_at is None or fvg_time is None:
            continue
        delta_seconds = abs((fvg_time - confirmed_at).total_seconds())
        if delta_seconds <= 8 * 60 * 60:
            return True
    return False


def _as_mapping(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    if hasattr(raw, "model_dump"):
        return raw.model_dump(mode="json")
    if hasattr(raw, "__dict__"):
        return raw.__dict__
    return {}


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
