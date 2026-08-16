"""POI ranking must reproduce how a trader chooses between zones.

The regression case is the CADJPY 4H supply at 112.828-113.721 that the founder
identified by eye. Detection used to delete it (its body was 0.106 of its range,
below the 0.75 body floor) and the founder had to point at the chart to prove it
existed. It is now emitted, and these tests hold the line on the thing that made
it valid: it is the origin of the departure that broke structure. Its body is
still thin. That must not cost it a single point.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from smc_desk.perception.poi_quality import (
    classify_location,
    freshness_of,
    location_alignment,
    rank_pois,
    score_poi,
    select_primary,
)


def make_poi(
    object_id: str,
    direction: str = "bearish",
    *,
    low: float = 100.0,
    high: float = 101.0,
    caused: bool = True,
    scope: str = "external",
    displacement: float = 1.0,
    mitigation: str = "untouched",
    activity: str = "active",
    body_ratio: float = 0.5,
    timeframe: str = "4h",
) -> dict:
    return {
        "object_id": object_id,
        "direction": direction,
        "price_low": low,
        "price_high": high,
        "timeframe": timeframe,
        "activity_status": activity,
        "mitigation_status": mitigation,
        "metadata": {"linked_break_scope": scope},
        "evidence": {
            "caused_structure_break": caused,
            "poi_grade": caused,
            "displacement_atr": displacement,
            "body_ratio": body_ratio,
            "structure_scope": scope,
        },
    }


# -- the founder's zone -------------------------------------------------------

CADJPY_SUPPLY = make_poi(
    "ob-cadjpy-0731",
    "bearish",
    low=112.828,
    high=113.721,
    caused=True,
    scope="external",
    displacement=1.9,
    body_ratio=0.106,  # far below the old 0.75 floor
)


def test_thin_body_costs_nothing() -> None:
    """The founder's zone must score identically to a fat-bodied twin.

    Body ratio is a recorded fact, not a ranking input. If this test ever fails,
    the body filter has crept back in through the scorer.
    """
    fat = dict(CADJPY_SUPPLY)
    fat["object_id"] = "ob-fat-twin"
    fat["evidence"] = {**CADJPY_SUPPLY["evidence"], "body_ratio": 0.92}

    thin_score = score_poi(CADJPY_SUPPLY, equilibrium=114.5, current_price=113.0)
    fat_score = score_poi(fat, equilibrium=114.5, current_price=113.0)

    assert thin_score is not None and fat_score is not None
    assert thin_score.score == fat_score.score


def test_founder_zone_outranks_a_nearer_uncaused_zone() -> None:
    """Proximity is a tie-break, never a reason.

    A zone sitting right under price but with no structure-breaking departure
    must lose to the zone that owns the move, even from further away.
    """
    nearer_but_idle = make_poi(
        "ob-near-idle",
        "bearish",
        low=113.90,
        high=114.05,  # closer to 113.0? no -- but closer than 113.27 midpoint? see below
        caused=False,
        scope="internal",
        displacement=0.1,
    )
    ranked = rank_pois(
        [nearer_but_idle, CADJPY_SUPPLY],
        equilibrium=114.5,
        current_price=113.95,  # sits inside the idle zone, far from the founder's
    )
    assert [poi.object_id for poi in ranked][0] == "ob-cadjpy-0731"


# -- the ordering itself ------------------------------------------------------


def test_causation_beats_scope() -> None:
    """Causation is the strongest criterion, so it must survive a scope deficit."""
    caused_internal = make_poi("caused-internal", caused=True, scope="internal")
    idle_external = make_poi("idle-external", caused=False, scope="external")
    ranked = rank_pois([idle_external, caused_internal])
    assert ranked[0].object_id == "caused-internal"


def test_external_outranks_internal_when_all_else_equal() -> None:
    ranked = rank_pois(
        [make_poi("internal", scope="internal"), make_poi("external", scope="external")]
    )
    assert [poi.object_id for poi in ranked] == ["external", "internal"]


def test_supply_in_premium_outranks_supply_in_discount() -> None:
    """Location is an SMC criterion, not decoration: sell high, buy low."""
    premium = make_poi("premium-supply", "bearish", low=120.0, high=121.0)
    discount = make_poi("discount-supply", "bearish", low=100.0, high=101.0)
    ranked = rank_pois([discount, premium], equilibrium=110.0)
    assert [poi.object_id for poi in ranked] == ["premium-supply", "discount-supply"]
    assert ranked[0].location == "premium"
    assert ranked[1].location == "discount"


def test_demand_wants_discount_not_premium() -> None:
    premium_demand = make_poi("premium-demand", "bullish", low=120.0, high=121.0)
    discount_demand = make_poi("discount-demand", "bullish", low=100.0, high=101.0)
    ranked = rank_pois([premium_demand, discount_demand], equilibrium=110.0)
    assert ranked[0].object_id == "discount-demand"


def test_fresh_outranks_partially_mitigated() -> None:
    ranked = rank_pois(
        [make_poi("partial", mitigation="partial"), make_poi("fresh", mitigation="untouched")]
    )
    assert [poi.object_id for poi in ranked] == ["fresh", "partial"]


def test_proximity_only_separates_otherwise_identical_zones() -> None:
    near = make_poi("near", low=109.0, high=110.0)
    far = make_poi("far", low=130.0, high=131.0)
    # Equilibrium omitted so location cannot separate them; both score the same.
    ranked = rank_pois([far, near], current_price=109.5)
    assert ranked[0].score == ranked[1].score
    assert ranked[0].object_id == "near"


# -- exclusions and edges -----------------------------------------------------


def test_spent_zones_are_hidden_by_default_but_recoverable() -> None:
    """A consumed zone is not a candidate, but it is still history worth reading."""
    consumed = make_poi("consumed", activity="terminal", mitigation="full")
    assert rank_pois([consumed]) == []
    assert len(rank_pois([consumed], include_spent=True)) == 1


def test_direction_filter_selects_one_side() -> None:
    ranked = rank_pois(
        [make_poi("supply", "bearish"), make_poi("demand", "bullish")], direction="bullish"
    )
    assert [poi.object_id for poi in ranked] == ["demand"]


def test_missing_geometry_is_dropped_not_guessed() -> None:
    assert score_poi({"object_id": "no-price", "direction": "bearish"}) is None
    assert rank_pois([{"object_id": "no-price"}]) == []


def test_inverted_prices_are_normalised() -> None:
    scored = score_poi(make_poi("inverted", low=101.0, high=100.0))
    assert scored is not None
    assert scored.price_low == 100.0 and scored.price_high == 101.0


def test_select_primary_keeps_the_alternates() -> None:
    """A choice without a runner-up is not a choice."""
    primary, alternates = select_primary(
        [make_poi("best"), make_poi("second", scope="internal"), make_poi("third", caused=False)]
    )
    assert primary is not None and primary.object_id == "best"
    assert [poi.object_id for poi in alternates] == ["second", "third"]


def test_select_primary_on_empty_input_refuses_rather_than_invents() -> None:
    assert select_primary([]) == (None, [])


# -- the reasons are the point ------------------------------------------------


def test_every_score_states_why_it_placed() -> None:
    scored = score_poi(CADJPY_SUPPLY, equilibrium=114.5, current_price=113.0)
    assert scored is not None
    joined = " | ".join(scored.reasons).lower()
    assert "structure" in joined
    assert "external" in joined
    assert "discount" in joined  # 113.27 midpoint sits below the 114.5 equilibrium
    assert "fresh" in joined


def test_wrong_side_of_equilibrium_is_named_in_the_reasons() -> None:
    scored = score_poi(make_poi("bad-location", "bearish", low=100.0, high=101.0), equilibrium=110.0)
    assert scored is not None
    assert any("wrong side of equilibrium" in reason for reason in scored.reasons)


# -- component helpers --------------------------------------------------------


@pytest.mark.parametrize(
    ("midpoint", "equilibrium", "expected"),
    [
        (120.0, 110.0, "premium"),
        (100.0, 110.0, "discount"),
        (110.0, 110.0, "equilibrium"),
        (110.0, None, "unknown"),
    ],
)
def test_classify_location(midpoint: float, equilibrium: float | None, expected: str) -> None:
    assert classify_location("bearish", midpoint, equilibrium) == expected


def test_unknown_location_is_neutral_not_penalised() -> None:
    """Without a dealing range the system must not invent a location verdict."""
    assert location_alignment("bearish", "unknown") == 0.5
    assert location_alignment("bearish", "equilibrium") == 0.5


def test_freshness_reads_both_activity_and_mitigation() -> None:
    assert freshness_of({"mitigation_status": "untouched"}) == ("fresh", 1.0)
    assert freshness_of({"mitigation_status": "partial"}) == ("partial", 0.5)
    assert freshness_of({"mitigation_status": "full"}) == ("spent", 0.0)
    assert freshness_of({"activity_status": "terminal"}) == ("spent", 0.0)


def test_ranking_is_deterministic_for_identical_zones() -> None:
    """Two zones that tie on everything must not reorder between runs."""
    zones = [make_poi("zebra"), make_poi("alpha")]
    first = [poi.object_id for poi in rank_pois(zones)]
    second = [poi.object_id for poi in rank_pois(list(reversed(zones)))]
    assert first == second == ["alpha", "zebra"]


# -- the weights are frozen pending calibration -------------------------------


def test_ranking_weights_match_the_sealed_revision() -> None:
    """The weights may only be what the sealed revision document says they are.

    They were frozen behind a tripwire so that moving them would require a
    written, hash-sealed justification rather than a quiet edit. That happened
    once: specs/POI_WEIGHT_REVISION_V1.yaml, sealed BEFORE the change was
    applied, recording the out-of-sample evidence for location, the absence of
    measured lift for causation, and the conditions that would reverse either.

    Changing a weight again is allowed. Doing it without amending that document
    first is not, and this test is where that gets noticed.
    """
    import yaml

    from smc_desk.data.hashing import file_sha256
    from smc_desk.perception import poi_quality

    root = Path(__file__).resolve().parents[2]
    spec = root / "specs" / "POI_WEIGHT_REVISION_V1.yaml"
    seal = root / "specs" / "POI_WEIGHT_REVISION_V1.sha256"
    assert file_sha256(spec) == seal.read_text(encoding="utf-8").strip(), (
        "the weight revision document has been edited since it was sealed"
    )

    revision = yaml.safe_load(spec.read_text(encoding="utf-8"))["revision"]
    actual = {
        "location": poi_quality.WEIGHT_LOCATION,
        "causation": poi_quality.WEIGHT_CAUSATION,
        "scope": poi_quality.WEIGHT_SCOPE,
        "displacement": poi_quality.WEIGHT_DISPLACEMENT,
        "freshness": poi_quality.WEIGHT_FRESHNESS,
    }
    for name, entry in revision.items():
        assert actual[name] == entry["to"], f"{name} is {actual[name]}, sealed says {entry['to']}"
    assert abs(sum(actual.values()) - 1.0) < 1e-9, "weights must remain a partition of one"


def test_location_is_now_the_heaviest_weight() -> None:
    """The substantive change: the only replicated factor leads the ranking."""
    from smc_desk.perception import poi_quality

    assert poi_quality.WEIGHT_LOCATION == max(
        poi_quality.WEIGHT_LOCATION, poi_quality.WEIGHT_CAUSATION,
        poi_quality.WEIGHT_SCOPE, poi_quality.WEIGHT_DISPLACEMENT,
        poi_quality.WEIGHT_FRESHNESS,
    )


def test_location_now_separates_two_otherwise_identical_causal_zones() -> None:
    """Both caused the break; only one is on the right side of equilibrium.

    This is the behaviour the out-of-sample evidence bought: +8.1% on BTCUSDT
    and +9.9% on ETHUSDT for supply in premium over supply in discount.
    """
    premium = make_poi("premium-supply", "bearish", low=120.0, high=121.0)
    discount = make_poi("discount-supply", "bearish", low=100.0, high=101.0)
    ranked = rank_pois([discount, premium], equilibrium=110.0)
    assert [poi.object_id for poi in ranked] == ["premium-supply", "discount-supply"]
    # The gap must be material, not cosmetic: location now carries 0.30.
    assert ranked[0].score - ranked[1].score > 0.2


def test_the_founder_zone_still_ranks_above_an_idle_neighbour() -> None:
    """The CADJPY regression must survive a reweighting, not be broken by it."""
    idle = make_poi("idle", "bearish", low=113.90, high=114.05, caused=False, scope="internal")
    ranked = rank_pois([idle, CADJPY_SUPPLY], equilibrium=114.5, current_price=113.95)
    assert ranked[0].object_id == "ob-cadjpy-0731"


def test_the_supplement_is_sealed_and_points_at_the_revision_it_supplements() -> None:
    """A seal that gets amended when its own test returns an awkward result is not a seal.

    The falsification condition in POI_WEIGHT_REVISION_V1 was met -- location
    replicated out of sample on three further instruments, five of five overall.
    The regime dependence found alongside it is recorded in a supplement rather
    than edited into the original, so the original still says exactly what was
    committed to before the test ran.
    """
    import yaml

    from smc_desk.data.hashing import file_sha256

    root = Path(__file__).resolve().parents[2]
    supplement = root / "specs" / "POI_WEIGHT_REVISION_V1_SUPPLEMENT_R2.yaml"
    seal = root / "specs" / "POI_WEIGHT_REVISION_V1_SUPPLEMENT_R2.sha256"
    assert file_sha256(supplement) == seal.read_text(encoding="utf-8").strip()

    doc = yaml.safe_load(supplement.read_text(encoding="utf-8"))
    original = root / "specs" / "POI_WEIGHT_REVISION_V1.yaml"
    assert doc["supplements_sha256"] == file_sha256(original), (
        "the supplement no longer describes the revision it claims to supplement"
    )
    assert doc["falsification_test"]["result"] == "REPLICATED"
    assert doc["what_this_changes"]["weight"] == "unchanged at 0.30, because the preregistered condition was met"
    # The awkward number must stay attached to the happy one.
    assert doc["regime_dependence"]["in_sample_lift"]["SOLUSDT"] == -0.270
