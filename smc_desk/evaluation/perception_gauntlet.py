"""Versioned, fail-closed SMC perception gauntlet.

The gauntlet distinguishes detection (correct geometry) from perception
(correct causal meaning).  It never grades its own market answers: case scores
must come from an adjudicated record, while this module enforces completeness,
grounding, paraphrase consistency, faculty ordering, and promotion gates.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GauntletProbe:
    probe_id: str
    faculty: str
    title: str
    primary_prompt: str
    paraphrase_prompt: str
    evidence_requirements: tuple[str, ...]
    abstention_allowed: bool = True
    mechanical: bool = False


FACULTIES: dict[str, dict[str, Any]] = {
    "A": {"name": "time_honesty", "minimum_percent": 90.0, "stage": 1},
    "B": {"name": "break_grammar", "minimum_percent": 80.0, "stage": 2},
    "C": {"name": "protected_points_and_invalidation", "minimum_percent": 80.0, "stage": 2},
    "D": {"name": "liquidity_narrative", "minimum_percent": 80.0, "stage": 2},
    "E": {"name": "poi_causality", "minimum_percent": 80.0, "stage": 2},
    "F": {"name": "multi_timeframe_containment", "minimum_percent": 80.0, "stage": 2},
    "G": {"name": "ranges_premium_discount", "minimum_percent": 80.0, "stage": 2},
    "H": {"name": "story_reconstruction", "minimum_percent": 70.0, "stage": 3},
    "I": {"name": "abstention_and_calibration", "minimum_percent": 80.0, "stage": 3},
    "J": {"name": "adversarial_and_metamorphic", "minimum_percent": 90.0, "stage": 1},
    "K": {"name": "annotation_judgment", "minimum_percent": 80.0, "stage": 4},
}

_REQ = {
    "A": ("candle_ids", "first_knowable_candle", "decision_cutoff"),
    "B": ("structure_event_ids", "level_price", "confirmation_candles"),
    "C": ("protected_point_id", "causal_break_id", "invalidation_rule"),
    "D": ("liquidity_object_ids", "sequence_candle_ids", "falsifier"),
    "E": ("poi_object_ids", "origin_candles", "linked_break_id", "lifecycle"),
    "F": ("parent_event_id", "child_event_id", "containment_relation"),
    "G": ("active_range_id", "range_anchor_ids", "equilibrium_price"),
    "H": ("episode_event_ids", "causal_edges", "competing_story"),
    "I": ("missing_evidence", "abstention_condition", "calibration_basis"),
    "J": ("baseline_claim_signature", "transformed_claim_signature", "expected_invariants"),
    "K": ("annotation_object_ids", "source_candle_ids", "editorial_reason"),
}


def _p(
    probe_id: str,
    title: str,
    primary: str,
    paraphrase: str,
    *,
    mechanical: bool = False,
    abstention_allowed: bool = True,
) -> GauntletProbe:
    faculty = probe_id[0]
    return GauntletProbe(
        probe_id=probe_id,
        faculty=faculty,
        title=title,
        primary_prompt=primary,
        paraphrase_prompt=paraphrase,
        evidence_requirements=_REQ[faculty],
        abstention_allowed=abstention_allowed,
        mechanical=mechanical,
    )


PROBES: tuple[GauntletProbe, ...] = (
    _p("A1", "frozen_read", "Freeze at candle T. Read only what was knowable, then explain after T+50 what the T read was.", "At the T cutoff, what could you conclude without later candles, and which of those conclusions must remain historically unchanged?"),
    _p("A2", "swing_knowability", "At which exact candle close did this pivot first become a confirmed swing, and what was it before then?", "Name the first-knowable candle for the swing and its provisional lifecycle before confirmation."),
    _p("A3", "forming_htf", "The current 4H candle is incomplete. Which facts from it are admissible?", "Separate observations from a forming 4H bar from structure claims that require its close."),
    _p("A4", "story_versioning", "Show a read that changed later. Was the earlier point-in-time read wrong?", "Update a prior thesis after new evidence without retroactively rewriting the old state."),
    _p("B1", "wick_probe", "Price wicked beyond an external high and closed back inside. Classify it now and state both resolution paths.", "Does a wick-only penetration confirm structure, or remain a probe? Give the exact breakout and sweep confirmations."),
    _p("B2", "initial_direction_break", "After a range, the first directional break prints. Is it BOS?", "With no established trend, how must the first accepted break be labelled?"),
    _p("B3", "internal_choch", "1H internal structure broke bearish while the 4H protected low held. What changed?", "Can a child internal CHoCH reverse an intact parent leg? Classify the child event and parent bias."),
    _p("B4", "weak_external_break", "An opposing external break printed on weak overlapping candles. Do you accept reversal?", "Classify an external violation lacking displacement and follow-through, and state the evidence needed for MSS acceptance."),
    _p("B5", "timeframe_close_authority", "A level closed through on 1H but not 4H. On which timeframe is it broken?", "Distinguish a child close beyond a level from confirmation by the parent candle that owns the level."),
    _p("C1", "causal_protection", "Name the exact price that invalidates the bullish story and what that origin caused.", "Which protected point owns the narrative, and which causal event grants that protection?"),
    _p("C2", "protection_probe", "Price wicked through protection and reclaimed within two candles. Is the story dead?", "Classify a wick-only violation of the protected point and state when protection is actually invalidated."),
    _p("C3", "parent_origin_vs_refinement", "A deeper 4H origin contains a 1H origin for the same move. Which protects and which refines?", "Separate parent causal origin from nested execution refinement using lineage evidence."),
    _p("D1", "liquidity_before_displacement", "Which exact liquidity pools were engineered and taken before displacement?", "Reconstruct the pre-displacement liquidity sequence and cite every pool and candle."),
    _p("D2", "draw_on_liquidity", "What is price drawing toward, and who is vulnerable on the route?", "Rank the active unswept liquidity objective and the intermediate resting orders with reasons."),
    _p("D3", "sweep_or_break_commitment", "Commit: sweep or accepted break, and name the future evidence that flips the answer.", "Give one current lifecycle classification plus a precise observable falsifier."),
    _p("D4", "inducement_story", "Locate inducement in the pullback and the real POI behind it.", "Identify the front-run pool that traps early entries and explain how it delivers price into the causal zone."),
    _p("D5", "engineered_liquidity_narrative", "Equal highs were swept and price reversed quickly. Explain the mechanism.", "Narrate who supplied liquidity, what consumed it, and what the displacement implies about the origin."),
    _p("E1", "the_poi", "Which zone is the primary POI now, and what did it do to earn authority?", "Choose one causal zone and justify it by origin, displacement, break lineage, lifecycle, and range location."),
    _p("E2", "poi_mitigation_lifecycle", "An order block was tapped twice and body-closed through. What is its current status?", "Replay the zone's mitigation and invalidation history rather than calling it fresh from geometry."),
    _p("E3", "breaker_transition", "Price closed through demand and returned. What is the zone now?", "Does a body-close-through convert the failed block into a breaker, and what confirmation is still required?"),
    _p("E4", "nested_poi_lineage", "Overlapping 4H and 1H order blocks: same event or coincidence? Prove it.", "Use departure and break lineage to determine whether nested POIs share one causal episode."),
    _p("E5", "poi_defense_mechanism", "Why could this zone be defended, and where is that visible?", "Tie the zone to consumed liquidity, imbalance, structural consequence, and unfinished business without institutional mind-reading."),
    _p("F1", "leg_containment", "Map the 15m trend into the controlling 4H leg.", "Whose parent leg contains the child move, and is the child expanding, retracing, or reversing it?"),
    _p("F2", "opposing_child_recovery", "A bearish parent break is followed by bullish child structure. Is the child stale or contextual?", "Interpret sustained child recovery inside the later parent event without letting it silently flip the parent."),
    _p("F3", "control_transfer", "Which timeframe controls, and what event transfers control?", "State the narrative owner, the execution owner, and the exact handoff and return conditions."),
    _p("F4", "ltf_against_daily", "15m is textbook bullish while 1D is mid-displacement bearish. Is it tradeable?", "Classify a clean child setup against unresolved daily delivery and specify the only safe authority state."),
    _p("G1", "active_range", "Define the active dealing range, equilibrium, and POI location. Why these anchors?", "Select the controlling leg's range, prove its activation, and place the POI in premium or discount."),
    _p("G2", "two_sided_sweep_regime", "Both range sides were swept. What regime and what remains tradeable?", "After two-sided liquidity removal, should direction be asserted or withheld until acceptance?"),
    _p("H1", "campaign_summary", "Narrate the last 100 candles as a campaign in at most six evidence-linked sentences.", "Compress the chart into a causal episode: context, liquidity, displacement, consequence, retrace, and current objective."),
    _p("H2", "displacement_leg", "Describe the leg between sweep and break: origin, consumption, footprints, terminus.", "Reconstruct the beginning, delivery, and end of the displacement rather than listing isolated labels."),
    _p("H3", "strongest_competing_story", "Give the strongest evidence-grounded story in which the current thesis is wrong.", "Steelman the best competing interpretation and name the discriminator between the two stories."),
    _p("H4", "non_retroactive_update", "Update yesterday's thesis after today's new event without rewriting yesterday.", "Create a versioned narrative delta: prior state, new evidence, changed claims, preserved claims."),
    _p("I1", "correct_abstention", "Read a choppy mid-range news-hour chart. What is the trade?", "Decide whether evidence supports a setup; if not, specify the exact sequence that would create one."),
    _p("I2", "confidence_honesty", "How confident are you, and what measurement supports that number?", "Separate calibrated empirical probability from uncalibrated rule strength; do not invent precision."),
    _p("I3", "value_of_information", "Which single additional fact would most change this read?", "Name the highest-value unresolved discriminator and how each outcome changes the thesis."),
    _p("I4", "skill_vs_luck", "Given past calls and outcomes, distinguish skill from luck.", "Use process correctness and calibrated repeated evidence, not one realized winner, to judge a prior call."),
    _p("J1", "vertical_mirror", "Read the vertically mirrored price chart.", "Invert every price and verify that bullish and bearish semantics swap exactly while structure remains symmetric.", mechanical=True),
    _p("J2", "decimal_rescale", "Rescale prices by 0.0001 and rename the symbol. Read it again.", "Check that decimal magnitude and asset label cannot change non-price semantics or object identities.", mechanical=True),
    _p("J3", "one_candle_rollback", "Move the decision cutoff one candle before confirmation and repeat the read.", "Remove only the confirmation close and identify exactly which claims must downgrade while prior claims remain.", mechanical=True),
    _p("J4", "origin_truncation", "Truncate history so the true origin is outside the visible window. Where did the move originate?", "When causal origin is unavailable, abstain from inventing one and expose the missing-history boundary.", mechanical=True),
    _p("J5", "sweep_removal_twin", "Compare twins differing only by removal of the pre-break sweep.", "Change one sweep wick and verify that only sweep-dependent story, break-quality, and POI-conviction claims change.", mechanical=True),
    _p("J6", "flash_spike", "A single thin-liquidity wick fabricates a level violation. Annotate it.", "Inject one aberrant wick and ensure it becomes a probe/anomaly, not confirmed BOS or a rebuilt downstream story.", mechanical=True),
    _p("K1", "five_object_story", "Annotate with at most five objects, each serving one causal story.", "Choose the smallest professional annotation set that explains context, event, POI, liquidity, and conditional path."),
    _p("K2", "deletion_judgment", "From nine candidate annotations, delete at least four and justify each deletion.", "Act as an editor: remove stale, redundant, internal-noise, and story-irrelevant marks while preserving causal anchors."),
    _p("K3", "deliberate_bare_chart", "When is a deliberately bare chart correct? Produce one with an intent record.", "Distinguish evidence-driven omission from renderer failure and state why no semantic object earned a mark."),
    _p("K4", "annotation_traceability", "For every mark, cite the exact candles and evidence objects that caused it.", "Prove complete bidirectional traceability from rendered geometry to immutable source evidence."),
)

PROBE_INDEX = {probe.probe_id: probe for probe in PROBES}
EXPECTED_PROBE_IDS = tuple(probe.probe_id for probe in PROBES)


def gauntlet_protocol_manifest() -> dict[str, Any]:
    payload = {
        "schema": "smc_perception_gauntlet_protocol_v2",
        "version": "2.0.0",
        "probe_count": len(PROBES),
        "response_wordings_per_probe": 2,
        "score_meaning": {
            "0": "fails: wrong, hallucinated, ungrounded, or paraphrase-inconsistent",
            "1": "detects: correct anchored geometry without causal meaning",
            "2": "perceives: correct cause, consequence, falsifier, and evidence grounding",
        },
        "faculties": FACULTIES,
        "promotion_order": [
            {"stage": 1, "faculties": ["A", "J"], "meaning": "time and metamorphic integrity"},
            {"stage": 2, "faculties": ["B", "C", "D", "E", "F", "G"], "meaning": "structure and causality"},
            {"stage": 3, "faculties": ["H", "I"], "meaning": "story, abstention, calibration"},
            {"stage": 4, "faculties": ["K"], "meaning": "annotation judgment"},
        ],
        "probes": [asdict(probe) for probe in PROBES],
        "authority_contract": {
            "engine_self_scoring_allowed": False,
            "independent_adjudication_required": True,
            "evidence_ids_required": True,
            "paraphrase_inconsistency_forces_zero": True,
            "annotation_cannot_be_promoted_before_story_gate": True,
            "signal_allowed": False,
        },
    }
    payload["protocol_sha256"] = _hash(payload)
    return payload


def response_template(case_id: str) -> dict[str, Any]:
    manifest = gauntlet_protocol_manifest()
    return {
        "schema": "smc_perception_gauntlet_response_v2",
        "case_id": case_id,
        "protocol_sha256": manifest["protocol_sha256"],
        "responses": [
            {
                "probe_id": probe.probe_id,
                "primary": _answer_template(),
                "paraphrase": _answer_template(),
            }
            for probe in PROBES
        ],
        "self_score": None,
        "authority_contract": {"self_score_has_certification_authority": False, "signal_allowed": False},
    }


def validate_gauntlet_response(
    submission: Mapping[str, Any], *, known_evidence_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    issues: list[str] = []
    expected_hash = gauntlet_protocol_manifest()["protocol_sha256"]
    if submission.get("schema") != "smc_perception_gauntlet_response_v2":
        issues.append("invalid_response_schema")
    if submission.get("protocol_sha256") != expected_hash:
        issues.append("protocol_hash_mismatch")
    raw_responses = submission.get("responses")
    if not isinstance(raw_responses, list):
        raw_responses = []
        issues.append("responses_must_be_a_list")
    ids = [str(item.get("probe_id") or "") for item in raw_responses if isinstance(item, Mapping)]
    duplicates = sorted(probe_id for probe_id, count in Counter(ids).items() if probe_id and count > 1)
    missing = sorted(set(EXPECTED_PROBE_IDS).difference(ids))
    unknown = sorted(set(ids).difference(EXPECTED_PROBE_IDS))
    if duplicates:
        issues.append("duplicate_probe_ids:" + ",".join(duplicates))
    if missing:
        issues.append("missing_probe_ids:" + ",".join(missing))
    if unknown:
        issues.append("unknown_probe_ids:" + ",".join(unknown))
    known = set(map(str, known_evidence_ids or []))
    probe_results: dict[str, Any] = {}
    for item in raw_responses:
        if not isinstance(item, Mapping):
            issues.append("response_entry_not_object")
            continue
        probe_id = str(item.get("probe_id") or "")
        probe = PROBE_INDEX.get(probe_id)
        if probe is None or probe_id in probe_results:
            continue
        local_issues: list[str] = []
        sides: dict[str, Mapping[str, Any]] = {}
        for wording in ("primary", "paraphrase"):
            answer = item.get(wording)
            if not isinstance(answer, Mapping):
                local_issues.append(f"{wording}_answer_missing")
                continue
            sides[wording] = answer
            abstain = answer.get("abstain") is True
            answer_text = str(answer.get("answer") or "").strip()
            evidence_ids = answer.get("evidence_contract_ids")
            if not isinstance(evidence_ids, list):
                local_issues.append(f"{wording}_evidence_ids_not_list")
                evidence_ids = []
            if not abstain and not answer_text:
                local_issues.append(f"{wording}_answer_empty")
            if abstain and not probe.abstention_allowed:
                local_issues.append(f"{wording}_abstention_not_allowed")
            if not abstain and not evidence_ids:
                local_issues.append(f"{wording}_ungrounded_claim")
            if known:
                bad_ids = sorted(set(map(str, evidence_ids)).difference(known))
                if bad_ids:
                    local_issues.append(f"{wording}_unknown_evidence_ids:" + ",".join(bad_ids))
            signature = answer.get("claim_signature")
            if not abstain and not isinstance(signature, Mapping):
                local_issues.append(f"{wording}_claim_signature_missing")
            if abstain and not str(answer.get("resolution_condition") or "").strip():
                local_issues.append(f"{wording}_abstention_missing_resolution_condition")
        consistent = False
        if set(sides) == {"primary", "paraphrase"}:
            left = _normalized_signature(sides["primary"])
            right = _normalized_signature(sides["paraphrase"])
            consistent = left == right
            if not consistent:
                local_issues.append("paraphrase_claim_signature_mismatch")
        probe_results[probe_id] = {
            "schema_valid": not local_issues,
            "paraphrase_consistent": consistent,
            "issues": local_issues,
        }
        issues.extend(f"{probe_id}:{issue}" for issue in local_issues)
    return {
        "schema": "smc_perception_gauntlet_response_validation_v2",
        "case_id": submission.get("case_id"),
        "protocol_sha256": expected_hash,
        "probe_count": len(probe_results),
        "expected_probe_count": len(PROBES),
        "probe_results": probe_results,
        "issues": issues,
        "status": "PASS_CONTRACT" if not issues else "FAIL_CONTRACT",
        "semantic_correctness_adjudicated": False,
    }


def score_gauntlet_case(
    submission: Mapping[str, Any],
    adjudication: Mapping[str, Any],
    *,
    known_evidence_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    validation = validate_gauntlet_response(submission, known_evidence_ids=known_evidence_ids)
    raw_scores = adjudication.get("probe_scores") if isinstance(adjudication, Mapping) else None
    if not isinstance(raw_scores, Mapping):
        raw_scores = {}
    scores: dict[str, int] = {}
    forced_zero: dict[str, list[str]] = {}
    issues: list[str] = []
    for probe_id in EXPECTED_PROBE_IDS:
        try:
            score = int(raw_scores[probe_id])
        except (KeyError, TypeError, ValueError):
            score = 0
            issues.append(f"missing_or_invalid_adjudicated_score:{probe_id}")
        if score not in {0, 1, 2}:
            score = 0
            issues.append(f"adjudicated_score_out_of_range:{probe_id}")
        contract = validation["probe_results"].get(probe_id) or {}
        reasons = list(contract.get("issues") or [])
        if reasons:
            score = 0
            forced_zero[probe_id] = reasons
        scores[probe_id] = score
    faculty_scores = _faculty_percentages(scores)
    return {
        "schema": "smc_perception_gauntlet_case_score_v2",
        "case_id": submission.get("case_id"),
        "protocol_sha256": validation["protocol_sha256"],
        "adjudication_status": adjudication.get("adjudication_status", "unknown"),
        "probe_scores": scores,
        "score_distribution": {str(value): sum(score == value for score in scores.values()) for value in (0, 1, 2)},
        "faculty_scores": faculty_scores,
        "forced_zero": forced_zero,
        "issues": issues,
        "status": "SCORED_ADJUDICATED" if not issues and adjudication.get("adjudication_status") == "complete" else "INCOMPLETE_ADJUDICATION",
        "engine_self_score_used": False,
    }


def aggregate_gauntlet_case_scores(
    case_scores: Sequence[Mapping[str, Any]], *, minimum_cases: int = 30
) -> dict[str, Any]:
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    valid: list[Mapping[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for index, report in enumerate(case_scores):
        case_id = str(report.get("case_id") or "")
        if not case_id:
            rejected.append({"case_id": f"index-{index}", "reason": "missing_case_id"})
            continue
        if case_id in seen:
            duplicate_ids.append(case_id)
            continue
        seen.add(case_id)
        if report.get("schema") != "smc_perception_gauntlet_case_score_v2":
            rejected.append({"case_id": case_id, "reason": "wrong_schema"})
            continue
        if report.get("status") != "SCORED_ADJUDICATED":
            rejected.append({"case_id": case_id, "reason": "not_complete_adjudication"})
            continue
        probe_scores = report.get("probe_scores") or {}
        if set(probe_scores) != set(EXPECTED_PROBE_IDS):
            rejected.append({"case_id": case_id, "reason": "incomplete_probe_scores"})
            continue
        valid.append(report)
    combined: dict[str, list[int]] = {probe_id: [] for probe_id in EXPECTED_PROBE_IDS}
    for report in valid:
        for probe_id, score in report["probe_scores"].items():
            combined[probe_id].append(int(score))
    average_probe_scores = {
        probe_id: (sum(values) / len(values) if values else 0.0)
        for probe_id, values in combined.items()
    }
    faculty_scores = _faculty_percentages(average_probe_scores)
    gate_results = _promotion_gates(faculty_scores)
    enough_cases = len(valid) >= minimum_cases
    all_gates_pass = all(item["passed"] for item in gate_results.values())
    complete = enough_cases and all_gates_pass and not duplicate_ids and not rejected
    return {
        "schema": "smc_perception_gauntlet_cohort_score_v2",
        "status": "PASS_PROMOTION_GATES" if complete else "NOT_PASSED",
        "protocol_sha256": gauntlet_protocol_manifest()["protocol_sha256"],
        "valid_case_count": len(valid),
        "minimum_case_count": minimum_cases,
        "probe_count": len(PROBES),
        "responses_per_probe": 2,
        "faculty_scores": faculty_scores,
        "promotion_gates": gate_results,
        "duplicate_case_ids": sorted(set(duplicate_ids)),
        "rejected_cases": rejected,
        "engine_self_score_used": False,
        "signal_allowed": False,
    }


def _answer_template() -> dict[str, Any]:
    return {
        "answer": None,
        "abstain": None,
        "resolution_condition": None,
        "evidence_contract_ids": [],
        "claim_signature": None,
    }


def _normalized_signature(answer: Mapping[str, Any]) -> dict[str, Any]:
    if answer.get("abstain") is True:
        return {"abstain": True, "resolution_condition": str(answer.get("resolution_condition") or "").strip().lower()}
    signature = answer.get("claim_signature")
    return _normalize_json(signature if isinstance(signature, Mapping) else {})


def _normalize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_json(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        normalized = [_normalize_json(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _faculty_percentages(scores: Mapping[str, float | int]) -> dict[str, float]:
    output: dict[str, float] = {}
    for faculty in FACULTIES:
        ids = [probe.probe_id for probe in PROBES if probe.faculty == faculty]
        output[faculty] = round(sum(float(scores.get(probe_id, 0.0)) for probe_id in ids) / (2.0 * len(ids)) * 100.0, 6)
    return output


def _promotion_gates(faculty_scores: Mapping[str, float]) -> dict[str, dict[str, Any]]:
    stage_one = all(float(faculty_scores.get(name, 0.0)) >= FACULTIES[name]["minimum_percent"] for name in ("A", "J"))
    output: dict[str, dict[str, Any]] = {}
    for faculty, contract in FACULTIES.items():
        prerequisite = True
        if contract["stage"] >= 2:
            prerequisite = stage_one
        if contract["stage"] >= 3:
            prerequisite = prerequisite and all(
                float(faculty_scores.get(name, 0.0)) >= FACULTIES[name]["minimum_percent"]
                for name in ("B", "C", "D", "E", "F", "G")
            )
        if contract["stage"] >= 4:
            prerequisite = prerequisite and float(faculty_scores.get("H", 0.0)) >= FACULTIES["H"]["minimum_percent"]
        score = float(faculty_scores.get(faculty, 0.0))
        output[faculty] = {
            "name": contract["name"],
            "score_percent": score,
            "minimum_percent": contract["minimum_percent"],
            "prerequisite_passed": prerequisite,
            "passed": prerequisite and score >= contract["minimum_percent"],
        }
    return output


def _hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "EXPECTED_PROBE_IDS",
    "FACULTIES",
    "PROBES",
    "GauntletProbe",
    "aggregate_gauntlet_case_scores",
    "gauntlet_protocol_manifest",
    "response_template",
    "score_gauntlet_case",
    "validate_gauntlet_response",
]
