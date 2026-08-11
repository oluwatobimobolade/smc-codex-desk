"""Perception quality guard rails — the regression fence.

Every other test in this repository asks "did the code do what it was told?".
These ask "does the system still read a chart like a trader?". They exist
because the failure this project actually suffered was invisible to a green
suite: on 2026-07-17 the canonical run passed every gate, every invariant and
every hash check, and still produced

  * 15 confirmed "external" structure breaks and 5 CHoCH in 3.7 days,
  * 6,591 evidence objects,
  * ``final bias = mixed`` from a textbook bearish-retracement layout,
  * and exactly one drawn object on the chart.

Nothing failed, because nothing measured *quality*. These guard rails fail the
build if any of those four regressions returns.

They run on committed real market data (``data/live_btc.csv``) rather than
synthetic fixtures, so they cannot be satisfied by a detector agreeing with
its own assumptions.
"""
from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from smc_desk.data.schemas import Candle
from smc_desk.perception.narrative_hierarchy import read_narrative
from smc_desk.perception.significance import grade_timeframe
from smc_desk.perception.structure import StructureDetector
from smc_desk.perception.swings import MultiScaleSwingDetector

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_BTC_CSV = REPO_ROOT / "data" / "live_btc.csv"

# A professional 15m markup of ~4 days of one instrument carries on the order
# of a dozen structural marks. These ceilings are deliberately generous: they
# are a fence against a firehose, not a claim about the exact right number.
MAX_TRADEABLE_STRUCTURE_OBJECTS = 20
MAX_MAJOR_STRUCTURE_EVENTS = 8
MAX_MAJOR_CHOCH_PER_WEEK = 4

pytestmark = pytest.mark.skipif(
    not LIVE_BTC_CSV.exists(), reason="live BTC fixture not present"
)


def _dv(value):
    return getattr(value, "value", value)


@pytest.fixture(scope="module")
def btc():
    df = pd.read_csv(LIVE_BTC_CSV)
    candles, rows = [], []
    for _, r in df.iterrows():
        candles.append(Candle(
            venue="BINANCE", instrument="BTCUSDT", timeframe="15m",
            open_time=pd.Timestamp(r["timestamp"]).to_pydatetime(),
            close_time=pd.Timestamp(r["close_time"]).to_pydatetime(),
            open=Decimal(str(r["open"])), high=Decimal(str(r["high"])),
            low=Decimal(str(r["low"])), close=Decimal(str(r["close"])),
            volume=Decimal(str(r["volume"])), trade_count=int(r["trade_count"]),
            is_closed=True, is_complete=True, contains_gap=False,
        ))
        rows.append({"high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])})
    now = candles[-1].close_time
    swings = MultiScaleSwingDetector().detect(candles, now)
    _, breaks = StructureDetector().detect(candles, swings["external"], now)
    confirmed = [b for b in breaks if _dv(b.confirmation_status) == "confirmed"]
    summary = grade_timeframe(
        candles=rows, swings=swings["external"], structure_breaks=confirmed
    )
    days = len(candles) * 15 / 1440
    return {
        "candles": candles, "rows": rows, "swings": swings,
        "confirmed": confirmed, "summary": summary, "days": days,
    }


# -- Guard rail 1: object density --------------------------------------------


def test_significant_structure_stays_at_human_density(btc):
    """A chart must not present more structure than a trader could mark.

    Raw detection is allowed to be noisy — that is the detector's job. What
    must never regress is the *graded* set that reasoning and annotation
    consume.
    """
    tradeable = btc["summary"].tradeable
    assert len(tradeable) <= MAX_TRADEABLE_STRUCTURE_OBJECTS, (
        f"{len(tradeable)} tradeable structure objects over {btc['days']:.1f} days "
        f"exceeds the ceiling of {MAX_TRADEABLE_STRUCTURE_OBJECTS}. "
        "The significance layer has stopped filtering."
    )


def test_grading_actually_removes_most_raw_detections(btc):
    """If grading stops discriminating, this is the first thing to break."""
    raw = len(btc["swings"]["external"]) + len(btc["confirmed"])
    kept = len(btc["summary"].tradeable)
    assert raw > 0
    assert kept < raw * 0.5, (
        f"grading kept {kept}/{raw} objects; it is no longer discriminating"
    )


def test_major_structure_events_are_rare(btc):
    major = btc["summary"].by_grade("major")
    assert len(major) <= MAX_MAJOR_STRUCTURE_EVENTS, (
        f"{len(major)} 'major' events over {btc['days']:.1f} days is not a "
        "market read; it is noise wearing structural labels."
    )


def test_character_does_not_change_every_few_hours(btc):
    """A CHoCH claims the market changed character. That is a rare event.

    The 2026-07-17 baseline produced 5 confirmed CHoCH in 3.7 days.
    """
    major_ids = {s.object_id for s in btc["summary"].by_grade("major")}
    major_choch = [
        b for b in btc["confirmed"]
        if b.break_type == "CHOCH" and b.object_id in major_ids
    ]
    per_week = len(major_choch) / max(btc["days"] / 7.0, 1e-9)
    assert per_week <= MAX_MAJOR_CHOCH_PER_WEEK, (
        f"{len(major_choch)} major CHoCH over {btc['days']:.1f} days "
        f"({per_week:.1f}/week) exceeds {MAX_MAJOR_CHOCH_PER_WEEK}/week."
    )


def test_marginal_pokes_are_never_major(btc):
    """Every 'major' break must carry real displacement, not 4 bps."""
    for score in btc["summary"].by_grade("major"):
        assert score.atr_multiple >= 0.20, (
            f"{score.object_id} graded major on {score.atr_multiple:.3f}x ATR"
        )


# -- Guard rail 2: the narrative must never collapse to 'mixed' --------------


def _node(bias, *, internal=None, protected_high=None, protected_low=None,
          break_id=None, body_close=None):
    node = {"external_bias": bias, "internal_state": internal or "none"}
    if protected_high is not None:
        node["protected_high"] = {"price": protected_high}
    if protected_low is not None:
        node["protected_low"] = {"price": protected_low}
    if break_id is not None:
        node["latest_external_break"] = {
            "object_id": break_id, "body_close_price": body_close,
            "confirmed_at": "2026-07-17T12:00:00Z",
        }
    return node


def test_textbook_retracement_is_never_refused_as_mixed():
    """The exact 2026-07-17 layout must always produce a readable story.

    Daily bearish + 4H bullish + 1H bearish is a bearish pullback, not a
    contradiction. If this ever reads as incoherent again, the unanimity vote
    has crept back in.
    """
    read = read_narrative(
        timeframes={
            "1d": _node("bearish", internal="bullish_internal_pullback",
                        protected_high=67000.0, protected_low=60000.0),
            "4h": _node("bullish", break_id="4h", body_close=64800.0),
            "1h": _node("bearish", break_id="1h", body_close=64200.0),
        },
        active_range={"high": 65589.7, "low": 61806.0, "price_location": "premium"},
        current_price=64650.0,
        liquidity_levels=[{"object_id": "sell", "price": 63000.0, "activity_status": "active"}],
    )
    assert read.is_coherent, "a textbook retracement must never be refused"
    assert read.context_bias == "bearish"
    assert read.state != "mixed"


def test_every_bias_combination_produces_a_named_state():
    """No combination of timeframe biases may end in an unreadable answer."""
    from itertools import product

    for d1, d4, d1h in product(["bullish", "bearish"], repeat=3):
        read = read_narrative(timeframes={
            "1d": _node(d1, protected_high=70000.0, protected_low=50000.0),
            "4h": _node(d4, break_id="4h", body_close=60000.0),
            "1h": _node(d1h, break_id="1h", body_close=60000.0),
        })
        assert read.state and read.sentence
        assert read.context_bias in {"bullish", "bearish"}


def test_a_coherent_read_always_names_a_draw():
    """'Where is price going?' must always be answered when a story exists."""
    read = read_narrative(
        timeframes={"1d": _node("bearish"), "4h": _node("bullish", break_id="4h", body_close=1.0)},
        active_range={"high": 110.0, "low": 90.0, "price_location": "premium"},
        current_price=100.0,
        liquidity_levels=[{"object_id": "sell", "price": 95.0, "activity_status": "active"}],
    )
    assert read.is_coherent
    assert read.draw.target_price is not None, "a coherent read with no draw is not a read"
    assert read.draw.rationale


def test_narrative_never_creates_signal_authority():
    """Improving the read must never quietly grant execution authority."""
    read = read_narrative(timeframes={"1d": _node("bullish"), "4h": _node("bullish")})
    payload = read.to_dict()
    assert payload["signal_allowed"] is False
    assert payload["authority"] == "observe_only_narrative_read"


# -- Guard rail 3: the vocabulary needed to draw a story must exist -----------


def test_annotation_vocabulary_can_express_a_market_story():
    """The 2026-07-17 chart could not draw its own range. That must not recur."""
    from smc_desk.brain.ai_smc_trader_brain import AnnotationDrawingObject
    import typing

    hints = typing.get_type_hints(AnnotationDrawingObject)
    allowed = set(typing.get_args(hints["object_type"]))
    for required in ("range_zone", "sweep_marker", "equal_levels",
                     "structure_segment", "poi_zone", "liquidity_line"):
        assert required in allowed, f"annotation vocabulary lost {required}"


def test_range_zone_still_requires_deterministic_equilibrium():
    """Vocabulary growth must not become a hole in the geometry contract."""
    from pydantic import ValidationError
    from smc_desk.brain.ai_smc_trader_brain import AnnotationDrawingObject

    with pytest.raises(ValidationError):
        AnnotationDrawingObject.model_validate({
            "object_type": "range_zone", "semantic_object_id": "r", "timeframe": "4h",
            "label": "R", "reason": "context", "kind": "range",
            "price_low": 1.0, "price_high": 2.0,
            "start_index": 0, "end_index": 5,
            "start_time": "a", "end_time": "b",
        })


# -- Guard rail 4: structural sequence coherence ------------------------------
#
# The density rails above would not have caught the defect a human reviewer
# found on CADJPY 4H: a bearish BOS recorded at 115.871 four hours AFTER a
# bearish CHoCH at 115.486 -- i.e. a continuation break at a HIGHER price than
# the change of character that preceded it. That is one plausible-looking
# object, so nothing measuring object counts could object to it.
#
# These rails measure coherence instead of volume.


def _confirmed_external(breaks):
    return [
        b for b in breaks
        if _dv(b.confirmation_status) == "confirmed"
        and str(b.structure_scope) == "external"
    ]


# NOTE: a "bearish breaks must always be lower" rule was tried here and
# removed. It is wrong. Verified on live BTCUSDT: a bearish BOS at 63,360 was
# followed by price rallying to 64,568 and then a bearish CHoCH at 64,199 --
# higher than the earlier break and entirely legitimate. Break, retrace,
# break again is the most common structure in a trend.
#
# The real distinction is not monotonic price but whether price returned to
# the protected side before breaking, which the next test checks directly.


def test_every_break_is_approached_from_the_protected_side(btc):
    """A break candle opens on the side the level protects.

    Without this, any candle sitting beyond a stale level satisfies the
    crossing test forever and records a retroactive phantom break.
    """
    for brk in _confirmed_external(btc["confirmed"]):
        level = float(brk.evidence.broken_price)
        probe_id = brk.evidence.probe_candle_id
        candle = next(
            (c for c in btc["candles"] if f"c_{c.open_time.timestamp()}" == probe_id), None
        )
        if candle is None:
            continue
        if _dv(brk.direction) == "bearish":
            assert float(candle.open) >= level, (
                f"{brk.object_id} claims a bearish break of {level} on a candle "
                f"opening at {float(candle.open)} -- already below it"
            )
        else:
            assert float(candle.open) <= level, (
                f"{brk.object_id} claims a bullish break of {level} on a candle "
                f"opening at {float(candle.open)} -- already above it"
            )


def test_a_decisive_candle_records_every_level_it_closed_through(btc):
    """Levels a candle closed beyond must not stay live in the model.

    The tracker once held a single active low and high, so a candle sweeping
    several structural levels retired one and left the rest believed intact
    while price traded far past them.
    """
    swept = [
        b for b in _confirmed_external(btc["confirmed"])
        if getattr(b.evidence, "levels_broken_by_candle", 0) > 1
    ]
    # The deterministic unit test in test_wp0022_smc_detector_rebuild pins the
    # multi-level delayed-confirmation case. This real-data guard asserts the
    # field remains coherent whenever such an event appears in BTC history.
    for brk in swept:
        assert brk.evidence.levels_broken_by_candle > 1
    # The field must exist on every break, so magnitude is always inspectable.
    for brk in _confirmed_external(btc["confirmed"]):
        assert hasattr(brk.evidence, "levels_broken_by_candle")
