"""One SMC visual grammar, shared by every renderer.

Chart markup is how a reader checks whether the system understood the market.
If the drawing conventions drift between the matplotlib renderer and the
TradingView profile, the same evidence produces two different-looking charts
and neither can be trusted as a check on the other.

The conventions below follow the mainstream SMC/ICT drawing vocabulary as used
by LuxAlgo's Smart Money Concepts toolkit and taught across SMC courses:

* **Internal structure is dashed; swing (external) structure is solid.** This
  is the single most important visual distinction on an SMC chart, because it
  separates the noise inside a leg from the structure that owns the trend.
* **Swing structure carries larger text than internal structure**, so scope is
  readable without reading the label.
* **Swing points are labelled HH / HL / LH / LL**, which is how a reader
  verifies the structural read at a glance rather than trusting a bias word.
* **POI zones are boxes spanning their origin candles and extended rightward**
  to the review edge, because a zone is a level price may return to, not a
  historical event.
* **Bullish is green, bearish is red**, muted rather than saturated. Zones sit
  behind price at high transparency; price is never obscured.

Two rules are ours rather than convention, and both come from failures this
project actually had:

* **Marks closer than a fraction of ATR collide** and the weaker one is
  dropped. Rendering real BTCUSDT data produced an external BOS and its
  internal twin at the identical price, stacking two labels and hiding the
  more important one.
* **A chart carries a small object budget.** The system once had 6,591
  evidence objects available and drew one; the opposite failure — drawing
  everything — is just as unreadable.

This module holds no geometry. It never decides where a level is, only how an
already-certified level should look.
"""
from __future__ import annotations

from typing import Any, Mapping

# -- palette ------------------------------------------------------------------
# Muted rather than saturated: on a candle chart the price action must stay
# the most legible thing on screen.
PALETTE: dict[str, str] = {
    "bullish": "#0F8B7E",
    "bearish": "#D2544B",
    "neutral": "#6B7280",
    "ink": "#12181C",
    "muted_ink": "#5B6670",
    "grid": "#ECEFF1",
    "paper": "#FFFFFF",
    "candle_up": "#159A8C",
    "candle_down": "#E65353",
    "wick": "#242424",
    "range_line": "#8B93A1",
    "premium_fill": "#D2544B",
    "discount_fill": "#0F8B7E",
    "poi_bullish": "#0F8B7E",
    "poi_bearish": "#D2544B",
    "liquidity": "#8B93A1",
}

# Zone fills sit behind candles; these are deliberately faint.
ZONE_ALPHA = 0.16
RANGE_HALF_ALPHA = 0.06

# -- line grammar -------------------------------------------------------------
# matplotlib dash specifications, keyed by the meaning they carry.
LINE_STYLES: dict[str, Any] = {
    "solid": "-",
    "dashed": (0, (5, 4)),
    "dotted": (0, (2, 3)),
    "fine_dotted": (0, (1, 2)),
}

# Swing/external structure owns the trend and is drawn solid and heavier.
# Internal structure is subordinate: dashed and lighter.
STRUCTURE_WEIGHT = {"external": 2.0, "internal": 1.3}
STRUCTURE_STYLE = {"external": "solid", "internal": "dashed"}
STRUCTURE_FONTSIZE = {"external": 9.5, "internal": 8.0}

# -- clutter --------------------------------------------------------------
# A professional context chart carries a handful of marks. These are ceilings,
# not targets.
OBJECT_BUDGET = {"context": 5, "watch_review": 7, "trade_plan": 8}
MAX_ZONES = 3
MAX_STRUCTURE_LINES = 3

# Two marks inside this multiple of ATR are visually one mark.
MIN_LABEL_SEPARATION_ATR = 0.35

# A POI zone is a level price may return to, so it extends rightward to the
# review edge rather than stopping at its origin candles.
POI_RIGHT_EXTENSION_FRACTION = 0.22
MIN_ZONE_WIDTH_BARS = 6


def direction_colour(direction: Any) -> str:
    """Bullish green, bearish red, anything else neutral grey."""
    value = str(direction or "").strip().lower()
    if value in {"bullish", "buy", "long", "up"}:
        return PALETTE["bullish"]
    if value in {"bearish", "sell", "short", "down"}:
        return PALETTE["bearish"]
    return PALETTE["neutral"]


def structure_style(scope: Any, kind: Any = None) -> dict[str, Any]:
    """Line grammar for a structure mark.

    Scope decides the visual weight, because internal-versus-external is the
    distinction a reader needs first. A CHoCH is never drawn dashed at swing
    scope: a change of character on external structure is the most important
    mark on the chart and must read as solid.
    """
    normalised = "internal" if str(scope or "").lower() == "internal" else "external"
    style_name = STRUCTURE_STYLE[normalised]
    if str(kind or "").lower() == "choch" and normalised == "external":
        style_name = "solid"
    return {
        "scope": normalised,
        "linestyle": LINE_STYLES[style_name],
        "style_name": style_name,
        "linewidth": STRUCTURE_WEIGHT[normalised],
        "fontsize": STRUCTURE_FONTSIZE[normalised],
    }


def swing_label(direction: Any, *, is_higher: bool | None) -> str:
    """HH / HL / LH / LL — the labels a reader uses to check the structure.

    ``is_higher`` compares this swing with the previous swing of the same side.
    ``None`` means there is no prior swing to compare against, so no claim is
    made rather than guessing one.
    """
    if is_higher is None:
        return ""
    value = str(direction or "").lower()
    if value == "bearish":                      # a swing HIGH
        return "HH" if is_higher else "LH"
    if value == "bullish":                      # a swing LOW
        return "HL" if is_higher else "LL"
    return ""


def zone_span(
    start_index: int,
    end_index: int,
    total_bars: int,
    *,
    minimum_width: int = MIN_ZONE_WIDTH_BARS,
) -> tuple[int, int]:
    """Extend a POI box rightward so it reads as a live level, not history."""
    start = max(0, min(int(start_index), max(total_bars - 1, 0)))
    end = max(int(end_index), start)
    extension = max(minimum_width, int(total_bars * POI_RIGHT_EXTENSION_FRACTION))
    return start, min(max(total_bars - 1, start), max(end, start + extension))


def collides(price: float, taken: list[float], atr: float | None) -> bool:
    """True when a mark would render on top of one already drawn."""
    if not taken:
        return False
    if atr and atr > 0:
        floor = atr * MIN_LABEL_SEPARATION_ATR
    else:
        floor = max(abs(price) * 0.0008, 1e-9)
    return any(abs(price - existing) <= floor for existing in taken)


def budget_for(template: Any) -> int:
    """Object ceiling for a chart template."""
    return OBJECT_BUDGET.get(str(template or "").lower(), OBJECT_BUDGET["context"])


def describe_grammar() -> dict[str, Any]:
    """Machine-readable summary, recorded in render manifests."""
    return {
        "schema": "smc_visual_grammar_v1",
        "internal_structure": "dashed, lighter, smaller label",
        "swing_structure": "solid, heavier, larger label",
        "external_choch": "always solid regardless of style hints",
        "swing_points": "labelled HH / HL / LH / LL when a prior swing exists",
        "poi_zones": "box over origin candles, extended right to the review edge",
        "premium_discount": "faint fill above/below equilibrium",
        "colours": {"bullish": PALETTE["bullish"], "bearish": PALETTE["bearish"]},
        "zone_alpha": ZONE_ALPHA,
        "object_budget": OBJECT_BUDGET,
        "min_label_separation_atr": MIN_LABEL_SEPARATION_ATR,
    }


__all__ = [
    "LINE_STYLES",
    "MAX_STRUCTURE_LINES",
    "MAX_ZONES",
    "MIN_LABEL_SEPARATION_ATR",
    "OBJECT_BUDGET",
    "PALETTE",
    "RANGE_HALF_ALPHA",
    "STRUCTURE_FONTSIZE",
    "STRUCTURE_STYLE",
    "STRUCTURE_WEIGHT",
    "ZONE_ALPHA",
    "budget_for",
    "collides",
    "describe_grammar",
    "direction_colour",
    "structure_style",
    "swing_label",
    "zone_span",
]
