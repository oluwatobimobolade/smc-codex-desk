"""Dual-lens reconciliation: engine truth + vision gestalt.

The whole point of this module is to let two *independent* reads of the same
market check each other:

* The **engine lens** (deterministic OHLCV analysis in ``engine.py``) owns every
  number — levels, entry, stop, target, verdict. It cannot hallucinate, but it is
  blind to anything that is not in the candle math (trendlines, chart cleanliness,
  on-chart annotations, news icons, the human "does this look tradeable" gestalt).

* The **vision lens** (an AI looking at the actual chart screenshot, e.g. via Kimi
  WebBridge) sees the gestalt and context, and gives a *second opinion* on bias and
  location. It may also report zones it can see — but those are used only to
  *agree-check* the engine, never to supply tradeable prices.

Reconciliation produces an **agreement score** and a **combined confidence**. Two
independent lenses agreeing is a real confidence signal; disagreement is a flag to
stand aside. Vision may raise a hard ``veto`` that forces no-trade.

Hard rule enforced here: the trade's numbers always come from the engine. Vision
modulates confidence and can veto. It never writes a price into the plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- Vision lens schema -----------------------------------------------------
# This is what an AI reports after *looking at the chart only*. It can be
# produced by Claude reading a screenshot, by Kimi WebBridge + a vision model,
# or by any future model. The reconciler does not care who produced it.

@dataclass
class VisionRead:
    lens: str = "vision"
    source: str = "unspecified"            # e.g. "claude-opus", "kimi-webbridge+vision"
    timeframe: str = "15m"
    observed_bias: str = "neutral"          # bullish | bearish | neutral
    trend_description: str = ""
    structure_quality: str = "unknown"       # clean | choppy | messy | unknown
    structure_quality_score: float = 0.5     # 0..1, the "is this tradeable-looking" gestalt
    price_location: str = "unknown"          # at_lows | at_highs | mid_range | at_poi | above_poi | below_poi | unknown
    key_zones_seen: list[dict[str, Any]] = field(default_factory=list)  # {kind, low, high, note}
    visible_context: list[str] = field(default_factory=list)  # chart annotations, news icons, sessions
    patterns_seen: list[str] = field(default_factory=list)
    source_aligned: bool | None = None
    source_alignment_note: str | None = None
    tradeable_now: bool = False
    veto: bool = False
    veto_reason: str | None = None
    comment: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisionRead":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# --- helpers ----------------------------------------------------------------

def _overlap_ratio(a_low: float, a_high: float, b_low: float, b_high: float) -> float:
    """Fraction of the narrower band that the two price bands share (0..1)."""
    a_low, a_high = sorted((a_low, a_high))
    b_low, b_high = sorted((b_low, b_high))
    inter = max(0.0, min(a_high, b_high) - max(a_low, b_low))
    narrow = max(1e-9, min(a_high - a_low, b_high - b_low))
    return max(0.0, min(1.0, inter / narrow))


def _plan(engine_analysis: dict[str, Any]) -> dict[str, Any]:
    return engine_analysis.get("trade_plan", {}) or {}


def _engine_price(engine_analysis: dict[str, Any]) -> float | None:
    metrics = engine_analysis.get("metrics", {}) or {}
    value = metrics.get("latest_close")
    return float(value) if value is not None else None


def _engine_price_location(engine_analysis: dict[str, Any]) -> str:
    """Where the engine thinks price sits relative to its selected POI / range."""
    plan = _plan(engine_analysis)
    price = _engine_price(engine_analysis)
    poi = plan.get("selected_poi")
    if price is not None and isinstance(poi, dict):
        low, high = poi.get("low"), poi.get("high")
        if low is not None and high is not None:
            if low <= price <= high:
                return "at_poi"
            return "below_poi" if price < low else "above_poi"
    metrics = engine_analysis.get("metrics", {}) or {}
    lo, hi = metrics.get("range_low"), metrics.get("range_high")
    if price is not None and lo is not None and hi is not None and hi > lo:
        frac = (price - lo) / (hi - lo)
        if frac <= 0.33:
            return "at_lows"
        if frac >= 0.66:
            return "at_highs"
        return "mid_range"
    return "unknown"


def _source_mismatch_reported(vision: VisionRead) -> bool:
    if vision.source_aligned is False:
        return True
    text = " ".join(vision.visible_context + ([vision.source_alignment_note] if vision.source_alignment_note else []))
    lowered = text.lower()
    mismatch_markers = [
        "not the same feed",
        "not identical",
        "source mismatch",
        "sources differ",
        "not source aligned",
        "not aligned",
    ]
    return any(marker in lowered for marker in mismatch_markers)


# Location reads that are mutually compatible between the two lenses.
_LOCATION_COMPATIBLE = {
    ("at_poi", "at_poi"),
    ("below_poi", "at_lows"), ("below_poi", "below_poi"),
    ("above_poi", "at_highs"), ("above_poi", "above_poi"),
    ("at_lows", "at_lows"), ("at_highs", "at_highs"), ("mid_range", "mid_range"),
}


# --- reconciliation ---------------------------------------------------------

def reconcile(
    engine_analysis: dict[str, Any],
    vision_read: dict[str, Any] | VisionRead,
    vision_authority_mode: str = "observe_only"
) -> dict[str, Any]:
    vision = vision_read if isinstance(vision_read, VisionRead) else VisionRead.from_dict(vision_read)
    plan = _plan(engine_analysis)

    engine_dir = (plan.get("direction") or "neutral").lower()
    vision_dir = (vision.observed_bias or "neutral").lower()
    engine_loc = _engine_price_location(engine_analysis)
    vision_loc = (vision.price_location or "unknown").lower()

    agreements: list[str] = []
    conflicts: list[str] = []

    # 1) Direction (the heaviest weight). ----------------------------------
    if engine_dir == vision_dir and engine_dir in {"bullish", "bearish"}:
        direction_score = 1.0
        agreements.append(f"Both lenses read {engine_dir} bias.")
    elif "neutral" in {engine_dir, vision_dir}:
        direction_score = 0.5
        conflicts.append(f"Soft bias mismatch: engine={engine_dir}, vision={vision_dir}.")
    else:
        direction_score = 0.0
        conflicts.append(f"HARD direction conflict: engine={engine_dir}, vision={vision_dir}. Stand aside.")

    # 2) Location relative to the POI / range. -----------------------------
    if vision_loc == "unknown" or engine_loc == "unknown":
        location_score = 0.5
    elif (engine_loc, vision_loc) in _LOCATION_COMPATIBLE:
        location_score = 1.0
        agreements.append(f"Both agree on location (engine={engine_loc}, vision={vision_loc}).")
    else:
        location_score = 0.25
        conflicts.append(f"Location mismatch: engine={engine_loc}, vision={vision_loc}.")

    # 3) Zone confirmation: does a vision zone overlap the engine's POI? ----
    poi = plan.get("selected_poi") if isinstance(plan.get("selected_poi"), dict) else None
    zone_score = 0.5
    best_overlap = 0.0
    if poi and poi.get("low") is not None and poi.get("high") is not None:
        for zone in vision.key_zones_seen:
            if zone.get("low") is None or zone.get("high") is None:
                continue
            best_overlap = max(best_overlap, _overlap_ratio(poi["low"], poi["high"], zone["low"], zone["high"]))
        if vision.key_zones_seen:
            zone_score = best_overlap
            if best_overlap >= 0.4:
                agreements.append(
                    f"Vision independently saw a zone overlapping the engine POI "
                    f"({poi.get('label', 'POI')} {poi['low']:.2f}-{poi['high']:.2f}, overlap {best_overlap:.0%})."
                )
            else:
                conflicts.append("Vision did not confirm the engine's selected POI region.")

    # 4) Structure quality (vision-only gestalt). --------------------------
    quality_score = float(vision.structure_quality_score)
    source_mismatch = _source_mismatch_reported(vision)
    if source_mismatch:
        conflicts.append("Vision reports a chart/data source mismatch; treat agreement as weaker than same-feed agreement.")

    # Weighted agreement score. -------------------------------------------
    weights = {"direction": 0.40, "location": 0.25, "zone": 0.20, "quality": 0.15}
    agreement_score = round(
        weights["direction"] * direction_score
        + weights["location"] * location_score
        + weights["zone"] * zone_score
        + weights["quality"] * quality_score,
        3,
    )

    # Combined confidence: start from the engine, modulate by agreement. ----
    base_conf = float(plan.get("confidence", 0.0) or 0.0)
    factor = 1.0
    if direction_score == 1.0:
        factor *= 1.08
    elif direction_score == 0.0:
        factor *= 0.45
    if location_score >= 1.0:
        factor *= 1.05
    elif location_score <= 0.25:
        factor *= 0.9
    if best_overlap >= 0.4:
        factor *= 1.06
    if quality_score >= 0.66:
        factor *= 1.04
    elif quality_score < 0.4:
        factor *= 0.85
    if source_mismatch:
        factor *= 0.85
    
    combined_confidence = round(max(0.0, min(0.95, base_conf * factor)), 3)

    # Final verdict: engine verdict, modulated. Vision can veto or conflict
    # us out, but it can never *upgrade* a no-trade into a trade on its own.
    engine_verdict = plan.get("verdict", "unknown")
    if vision.veto:
        final_verdict = "No-Trade (vision veto)"
        conflicts.append(f"Vision veto: {vision.veto_reason or 'unspecified'}.")
        combined_confidence = min(combined_confidence, 0.2)
    elif direction_score == 0.0:
        final_verdict = "Conflict — stand aside"
        combined_confidence = min(combined_confidence, 0.3)
    else:
        final_verdict = engine_verdict

    # Enforce observe_only authority limits
    if vision_authority_mode == "observe_only":
        combined_confidence = base_conf
        final_verdict = engine_verdict

    if agreement_score >= 0.75:
        verdict_alignment = "strong_agreement"
    elif agreement_score >= 0.5:
        verdict_alignment = "partial_agreement"
    else:
        verdict_alignment = "disagreement"

    return {
        "lens_a": "engine",
        "lens_b": vision.source or "vision",
        "engine": {
            "direction": engine_dir,
            "verdict": engine_verdict,
            "setup_grade": plan.get("setup_grade"),
            "confluence_score": plan.get("confluence_score"),
            "confidence": base_conf,
            "price_location": engine_loc,
            "selected_poi": poi,
            "entry_zone": [plan.get("entry_low"), plan.get("entry_high")],
            "structural_invalidation": plan.get("structural_invalidation"),
            "execution_invalidation": plan.get("execution_invalidation") or plan.get("invalidation"),
            "invalidation": plan.get("invalidation"),
            "stop_buffer": plan.get("stop_buffer"),
            "stop_buffer_atr": plan.get("stop_buffer_atr"),
            "stop_quality": plan.get("stop_quality"),
            "targets": plan.get("targets", []),
            "risk_reward": plan.get("risk_reward"),
        },
        "vision": {
            "bias": vision_dir,
            "price_location": vision_loc,
            "structure_quality": vision.structure_quality,
            "structure_quality_score": quality_score,
            "patterns_seen": vision.patterns_seen,
            "visible_context": vision.visible_context,
            "tradeable_now": vision.tradeable_now,
            "veto": vision.veto,
            "source_aligned": vision.source_aligned,
            "source_alignment_note": vision.source_alignment_note,
        },
        "scores": {
            "direction": direction_score,
            "location": location_score,
            "zone": round(zone_score, 3),
            "quality": round(quality_score, 3),
        },
        "agreement_score": agreement_score,
        "verdict_alignment": verdict_alignment,
        "agreements": agreements,
        "conflicts": conflicts,
        "combined_confidence": combined_confidence,
        "final_verdict": final_verdict,
        "rule": "Engine owns all prices. Vision confirms, contextualizes, or vetoes — it never originates a level.",
    }


def render_markdown(recon: dict[str, Any], symbol: str = "", timeframe: str = "") -> str:
    eng = recon["engine"]
    vis = recon["vision"]
    sc = recon["scores"]
    header = f"{symbol} {timeframe}".strip()
    poi = eng.get("selected_poi") or {}
    poi_txt = (
        f"{poi.get('label', 'POI')} {poi['low']:.2f}-{poi['high']:.2f}"
        if poi.get("low") is not None else "none"
    )
    lines = [
        f"# Dual-Lens Reconciliation — {header}".rstrip(" —"),
        "",
        f"**Alignment: {recon['verdict_alignment'].replace('_', ' ').upper()}**  ·  "
        f"agreement score **{recon['agreement_score']:.2f}**  ·  "
        f"combined confidence **{recon['combined_confidence']:.2f}**",
        "",
        f"**Final verdict: {recon['final_verdict']}**",
        "",
        "| | Engine lens (numbers) | Vision lens (gestalt) |",
        "|---|---|---|",
        f"| Bias | {eng['direction']} | {vis['bias']} |",
        f"| Location | {eng['price_location']} | {vis['price_location']} |",
        f"| Verdict / quality | {eng['verdict']} (grade {eng.get('setup_grade')}) | "
        f"{vis['structure_quality']} ({vis['structure_quality_score']:.2f}) |",
        f"| Confidence | {eng['confidence']:.2f} | tradeable_now={vis['tradeable_now']} |",
        "",
        "## Component scores",
        f"- Direction: {sc['direction']:.2f}",
        f"- Location: {sc['location']:.2f}",
        f"- Zone confirmation: {sc['zone']:.2f}",
        f"- Structure quality: {sc['quality']:.2f}",
        "",
        "## Engine plan (authoritative numbers)",
        f"- Selected POI: {poi_txt}",
        f"- Entry zone: {eng['entry_zone']}",
        f"- Execution SL / invalidation: {eng['invalidation']}",
        f"- Structural invalidation: {eng.get('structural_invalidation')}",
        f"- Stop quality: {eng.get('stop_quality')} ({eng.get('stop_buffer_atr')} ATR)",
        f"- Targets: {eng['targets']}  ·  R:R {eng['risk_reward']}",
        "",
        "## Agreements",
    ]
    lines += [f"- {a}" for a in recon["agreements"]] or ["- (none)"]
    lines += ["", "## Conflicts"]
    lines += [f"- {c}" for c in recon["conflicts"]] or ["- (none)"]
    if vis.get("patterns_seen"):
        lines += ["", "## Vision saw"] + [f"- {p}" for p in vis["patterns_seen"]]
    if vis.get("visible_context"):
        lines += ["", "## On-chart context"] + [f"- {c}" for c in vis["visible_context"]]
    lines += ["", f"> {recon['rule']}", ""]
    return "\n".join(lines)
