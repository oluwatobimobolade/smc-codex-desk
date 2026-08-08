"""Deterministic annotation vocabulary for certified SMC evidence.

The AI decides which certified objects deserve attention. It does not get to
rename an FVG as an OB, an internal break as external structure, or a wick
probe as a confirmed break. This module is the single label authority shared
by the semantic-to-geometry bridge and its tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from smc_desk.brain.annotation_evidence import AnnotationEvidenceAnchor


@dataclass(frozen=True)
class AnnotationSemantic:
    label: str
    kind: str
    line_style: str


def certified_annotation_semantic(anchor: AnnotationEvidenceAnchor) -> AnnotationSemantic:
    """Return the only allowed visible label/style for an evidence anchor."""
    timeframe = anchor.timeframe.upper()
    direction = (anchor.direction or "unknown").lower()
    scope = (anchor.structure_scope or "external").lower()
    raw_kind = (anchor.kind or "").lower()

    if anchor.evidence_type == "structure":
        if anchor.is_wick_only_probe or anchor.confirmation_status not in {None, "confirmed"}:
            return AnnotationSemantic(f"{timeframe} Probe", "structure", "dotted")
        if raw_kind == "bos":
            prefix = "Internal " if scope == "internal" else ""
            return AnnotationSemantic(f"{timeframe} {prefix}BOS", "bos", "dashed" if scope == "internal" else "solid")
        if raw_kind == "choch":
            prefix = "Internal " if scope == "internal" else "External "
            return AnnotationSemantic(f"{timeframe} {prefix}CHoCH", "choch", "dashed" if scope == "internal" else "solid")
        prefix = "Internal " if scope == "internal" else "External "
        return AnnotationSemantic(f"{timeframe} {prefix}Structure", "structure", "dashed" if scope == "internal" else "solid")

    if anchor.evidence_type == "order_block":
        side = "Bullish" if direction == "bullish" else "Bearish" if direction == "bearish" else "Unresolved"
        return AnnotationSemantic(f"{timeframe} {side} OB", "order_block", "solid")

    if anchor.evidence_type == "fvg":
        side = "Bullish" if direction == "bullish" else "Bearish" if direction == "bearish" else "Unresolved"
        return AnnotationSemantic(f"{timeframe} {side} FVG", "fvg", "solid")

    if anchor.evidence_type == "swing_pivot":
        if "high" in raw_kind:
            return AnnotationSemantic(f"{timeframe} Protected High", "liquidity", "dotted")
        if "low" in raw_kind:
            return AnnotationSemantic(f"{timeframe} Protected Low", "liquidity", "dotted")

    if "eqh" in raw_kind or "equal_high" in raw_kind:
        return AnnotationSemantic(f"{timeframe} EQH / BSL", "liquidity", "dotted")
    if "eql" in raw_kind or "equal_low" in raw_kind:
        return AnnotationSemantic(f"{timeframe} EQL / SSL", "liquidity", "dotted")
    if "inducement" in raw_kind or raw_kind == "idm":
        return AnnotationSemantic(f"{timeframe} IDM", "idm", "dotted")
    return AnnotationSemantic(f"{timeframe} Liquidity", "liquidity", "dotted")


__all__ = ["AnnotationSemantic", "certified_annotation_semantic"]
