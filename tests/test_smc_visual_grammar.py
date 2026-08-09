"""Tests for the shared SMC visual grammar.

Chart markup is how a reader checks whether the system understood the market,
so the drawing conventions must not drift between the matplotlib renderer and
the TradingView profile. These pin the conventions themselves.

The distinction that matters most is internal versus swing structure. On a
real SMC chart that is the first thing a reader uses, and the system had no
visual expression of it at all before this.
"""
from __future__ import annotations

import pytest

from smc_desk.rendering import smc_visual_grammar as grammar


# -- the internal / swing distinction ------------------------------------------


def test_swing_structure_is_solid_and_heavier_than_internal():
    external = grammar.structure_style("external")
    internal = grammar.structure_style("internal")
    assert external["style_name"] == "solid"
    assert internal["style_name"] == "dashed"
    assert external["linewidth"] > internal["linewidth"]
    assert external["fontsize"] > internal["fontsize"]


def test_external_choch_is_always_solid():
    """A change of character on swing structure is the chart's loudest mark."""
    assert grammar.structure_style("external", "choch")["style_name"] == "solid"


def test_internal_choch_stays_dashed():
    """Internal CHoCH is timing evidence, not a trend change."""
    assert grammar.structure_style("internal", "choch")["style_name"] == "dashed"


def test_unknown_scope_is_treated_as_external():
    """Absent scope must not silently downgrade a mark to internal."""
    assert grammar.structure_style(None)["scope"] == "external"
    assert grammar.structure_style("")["style_name"] == "solid"


# -- swing point labels --------------------------------------------------------


def test_swing_labels_follow_the_hh_hl_lh_ll_convention():
    assert grammar.swing_label("bearish", is_higher=True) == "HH"
    assert grammar.swing_label("bearish", is_higher=False) == "LH"
    assert grammar.swing_label("bullish", is_higher=True) == "HL"
    assert grammar.swing_label("bullish", is_higher=False) == "LL"


def test_no_swing_label_is_claimed_without_a_prior_swing():
    """With nothing to compare against, make no claim rather than guess."""
    assert grammar.swing_label("bullish", is_higher=None) == ""


# -- colour --------------------------------------------------------------------


def test_direction_colour_is_conventional():
    assert grammar.direction_colour("bullish") == grammar.PALETTE["bullish"]
    assert grammar.direction_colour("bearish") == grammar.PALETTE["bearish"]
    assert grammar.direction_colour("unknown") == grammar.PALETTE["neutral"]


def test_colour_accepts_trader_synonyms():
    assert grammar.direction_colour("long") == grammar.PALETTE["bullish"]
    assert grammar.direction_colour("SHORT") == grammar.PALETTE["bearish"]


# -- zones ---------------------------------------------------------------------


def test_poi_zone_extends_rightward_to_read_as_a_live_level():
    """A POI is somewhere price may return to, not a historical event."""
    start, end = grammar.zone_span(10, 12, total_bars=100)
    assert end - start >= grammar.MIN_ZONE_WIDTH_BARS
    assert end > 12


def test_zone_never_runs_past_the_chart():
    start, end = grammar.zone_span(95, 99, total_bars=100)
    assert end <= 99


def test_zone_start_is_clamped_into_the_window():
    start, end = grammar.zone_span(-5, 3, total_bars=50)
    assert start == 0 and end > start


# -- collision -----------------------------------------------------------------


def test_marks_inside_the_separation_floor_collide():
    """Two labels within a fraction of ATR render as one and hide each other."""
    assert grammar.collides(64000.0, [64010.0], atr=1000.0) is True


def test_separated_marks_do_not_collide():
    assert grammar.collides(64000.0, [62000.0], atr=1000.0) is False


def test_collision_falls_back_to_a_relative_floor_without_atr():
    assert grammar.collides(64000.0, [64000.5], atr=None) is True
    assert grammar.collides(64000.0, [61000.0], atr=None) is False


def test_first_mark_never_collides():
    assert grammar.collides(64000.0, [], atr=1000.0) is False


# -- budget --------------------------------------------------------------------


def test_context_charts_carry_the_smallest_budget():
    assert grammar.budget_for("context") < grammar.budget_for("trade_plan")


def test_unknown_template_falls_back_to_the_strictest_budget():
    assert grammar.budget_for("nonsense") == grammar.OBJECT_BUDGET["context"]


# -- the grammar is self-describing --------------------------------------------


def test_grammar_records_itself_for_the_render_manifest():
    described = grammar.describe_grammar()
    assert described["schema"] == "smc_visual_grammar_v1"
    assert "dashed" in described["internal_structure"]
    assert "solid" in described["swing_structure"]
    assert described["min_label_separation_atr"] == grammar.MIN_LABEL_SEPARATION_ATR


def test_zones_sit_behind_price():
    """Annotation must never obscure the candles it describes."""
    assert 0 < grammar.ZONE_ALPHA < 0.3
    assert 0 < grammar.RANGE_HALF_ALPHA < grammar.ZONE_ALPHA
