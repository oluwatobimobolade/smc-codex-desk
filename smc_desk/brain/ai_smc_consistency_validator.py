"""Consistency validator for AI SMC trader decisions.

The validator is the authority boundary. It converts unsupported model claims
into REVIEW_REQUIRED and blocks official charts from using unvalidated levels.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from smc_desk.brain.ai_smc_trader_brain import AISMCDecision, MINIMUM_RR, REASONING_ORDER


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["hard", "warning"] = "hard"
    message: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, populate_by_name=True)

    schema_: Literal["ai_smc_validation_result_v1"] = Field(default="ai_smc_validation_result_v1", alias="schema")
    status: Literal["VALIDATED", "REVIEW_REQUIRED"]
    decision: AISMCDecision
    official_decision: dict[str, Any]
    issues: list[ValidationIssue] = Field(default_factory=list)
    smc_model_validity: Literal["valid", "invalid"] = "valid"
    trade_plan_validity: Literal["passed", "failed"] = "passed"

    @property
    def is_validated(self) -> bool:
        return self.status == "VALIDATED"


def validate_ai_smc_decision(
    decision: AISMCDecision,
    evidence_pack: Mapping[str, Any],
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _check_reasoning_order(decision, issues)
    _check_bias_alignment(decision, issues)
    _check_no_1m_entry(decision, issues)
    _check_chart_eligibility(decision, issues)
    _check_trade_ready_preconditions(decision, issues)
    _check_active_range(decision, evidence_pack, issues)
    _check_direction_vs_active_range(decision, evidence_pack, issues)
    _check_claimed_sweep(decision, evidence_pack, issues)
    _check_claimed_displacement(decision, evidence_pack, issues)
    _check_active_poi(decision, evidence_pack, issues)
    _check_structural_stop(decision, issues)
    _check_target_logic(decision, evidence_pack, issues)
    _check_rr(decision, issues)
    _check_label_budget(decision, issues)
    _check_self_review(decision, issues)

    mapped_prices = _check_anchors_and_grounding(decision, evidence_pack, issues)
    _check_liquidity_status(decision, evidence_pack, issues)

    # SMC Doctrine vs Trade Plan categorisation
    smc_doctrine_issue_codes = {
        "direction_bias_mismatch",
        "displacement_direction_mismatch",
        "forbidden_1m_entry",
        "active_range_invalid_bounds",
        "active_range_summary_source_forbidden",
        "active_range_claim_without_authority",
        "active_range_authority_invalid",
        "active_range_missing_selected_range",
        "active_range_mismatch_authority",
        "active_range_source_not_structural",
        "active_range_too_wide",
        "direction_conflicts_with_active_range",
        "sweep_claim_without_candidate",
        "sweep_claim_unmatched",
        "reversal_requires_sweep",
        "displacement_without_candidate",
        "displacement_missing_evidence_id",
        "displacement_direction_unmatched",
        "poi_without_candidate",
        "poi_claim_unmatched",
        "stop_not_structural_invalidation",
        "bearish_stop_not_above_entry",
        "bearish_stop_inside_poi",
        "bullish_stop_not_below_entry",
        "bullish_stop_inside_poi",
        "bearish_target_above_entry",
        "bullish_target_below_entry",
        "target_not_model_completion_liquidity",
        "swept_low_classified_as_fresh_ssl",
    }

    # Calculate statuses
    has_doctrine_hard_issue = False
    has_trade_plan_hard_issue = False

    for issue in issues:
        if issue.severity == "hard":
            if issue.code in smc_doctrine_issue_codes:
                has_doctrine_hard_issue = True
            else:
                has_trade_plan_hard_issue = True

    smc_model_validity = "invalid" if has_doctrine_hard_issue else "valid"
    trade_plan_validity = "failed" if (has_doctrine_hard_issue or has_trade_plan_hard_issue) else "passed"

    hard_issues = [issue for issue in issues if issue.severity == "hard"]
    status: Literal["VALIDATED", "REVIEW_REQUIRED"] = "REVIEW_REQUIRED" if hard_issues else "VALIDATED"
    official = decision.to_official_dict()

    # Inject resolved mapped prices into the official output
    if mapped_prices.get("entry") is not None:
        official["entry_plan"]["mapped_entry_price"] = mapped_prices["entry"]
    if mapped_prices.get("stop") is not None:
        official["stop_loss_plan"]["mapped_stop_price"] = mapped_prices["stop"]
    if mapped_prices.get("invalidation") is not None:
        official["invalidation"]["mapped_invalidation_price"] = mapped_prices["invalidation"]
    
    if "target_plan" in official and "targets" in official["target_plan"]:
        for idx, resolved_t in enumerate(mapped_prices.get("targets", [])):
            if idx < len(official["target_plan"]["targets"]):
                official["target_plan"]["targets"][idx]["mapped_target_price"] = resolved_t

    if status != "VALIDATED":
        official = strip_trade_plan_for_review(official, issues)
    else:
        official["validation_status"] = "VALIDATED"
        official["validation_issues"] = [issue.model_dump(mode="json") for issue in issues]
    
    # Expose validation statuses inside official_decision payload
    official["smc_model_validity"] = smc_model_validity
    official["trade_plan_validity"] = trade_plan_validity
    if smc_model_validity == "valid" and trade_plan_validity == "failed":
        if "rr_below_minimum" in [i.code for i in hard_issues]:
            official["validation_message"] = "SMC thesis valid, but trade plan rejected by user RR profile."
        else:
            official["validation_message"] = "SMC thesis valid, but trade plan failed quality/preference filters."

    return ValidationResult(
        status=status,
        decision=decision,
        official_decision=official,
        issues=issues,
        smc_model_validity=smc_model_validity,
        trade_plan_validity=trade_plan_validity
    )


def assert_validated_official_decision(result: ValidationResult) -> None:
    if result.status != "VALIDATED":
        raise AssertionError("Official AI SMC decision is not validated.")


def strip_trade_plan_for_review(official: Mapping[str, Any], issues: Sequence[ValidationIssue]) -> dict[str, Any]:
    """Remove executable trade levels from a review-required official decision.

    Both normal validation failures and context-depth downgrades use this exact
    path so entry/SL/TP stripping cannot drift between call sites.
    """
    stripped = dict(official)
    stripped["official_state"] = "REVIEW_REQUIRED"
    entry_plan = dict(stripped.get("entry_plan") or {})
    entry_plan["entry_ready"] = False
    entry_plan["entry_price"] = None
    stripped["entry_plan"] = entry_plan

    stop_loss_plan = dict(stripped.get("stop_loss_plan") or {})
    stop_loss_plan["stop_price"] = None
    stripped["stop_loss_plan"] = stop_loss_plan

    target_plan = dict(stripped.get("target_plan") or {})
    target_plan["targets"] = []
    stripped["target_plan"] = target_plan

    rr_status = dict(stripped.get("rr_status") or {})
    rr_status["rr"] = None
    rr_status["pass_rr"] = False
    stripped["rr_status"] = rr_status

    annotation_plan = dict(stripped.get("annotation_plan") or {})
    annotation_plan["chart_template"] = "review_chart"
    annotation_plan["show_trade_box"] = False
    annotation_plan["levels"] = [
        level
        for level in annotation_plan.get("levels", []) or []
        if isinstance(level, Mapping) and level.get("kind") not in {"entry", "stop", "target"}
    ]
    stripped["annotation_plan"] = annotation_plan

    stripped["validation_status"] = "REVIEW_REQUIRED"
    stripped["validation_issues"] = [issue.model_dump(mode="json") for issue in issues]
    return stripped


def _issue(issues: list[ValidationIssue], code: str, message: str, severity: str = "hard") -> None:
    issues.append(ValidationIssue(code=code, message=message, severity=severity))  # type: ignore[arg-type]


def _check_reasoning_order(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    if decision.annotation_plan.reasoning_order != REASONING_ORDER:
        _issue(issues, "reasoning_order_mismatch", "AI reasoning order does not match the locked SMC sequence.")


def _check_bias_alignment(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    final_bias = decision.bias_summary.final_bias
    if decision.direction in {"bullish", "bearish"} and final_bias in {"bullish", "bearish"} and decision.direction != final_bias:
        _issue(issues, "direction_bias_mismatch", "Decision direction conflicts with bias_summary.final_bias.")
    if decision.displacement_assessment.direction in {"bullish", "bearish"} and decision.direction in {"bullish", "bearish"}:
        if decision.displacement_assessment.direction != decision.direction:
            _issue(issues, "displacement_direction_mismatch", "Displacement direction conflicts with final direction.")


def _check_no_1m_entry(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    for field_name, value in {
        "entry_timeframe": decision.entry_plan.entry_timeframe,
        "refinement_timeframe": decision.entry_plan.refinement_timeframe,
    }.items():
        if str(value or "").lower() == "1m":
            _issue(issues, "forbidden_1m_entry", f"{field_name} cannot be 1m for an official entry plan.")


def _check_chart_eligibility(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    plan = decision.annotation_plan
    if decision.official_state == "TRADE_PLAN_READY":
        if plan.chart_template != "trade_plan_chart":
            _issue(issues, "trade_ready_requires_trade_chart", "TRADE_PLAN_READY must use trade_plan_chart.")
        if not plan.show_trade_box:
            _issue(issues, "trade_ready_requires_trade_box", "TRADE_PLAN_READY must explicitly show the trade box.")
        if not decision.entry_plan.entry_ready:
            _issue(issues, "trade_ready_requires_entry_ready", "TRADE_PLAN_READY requires entry_ready=true.")
        if decision.entry_plan.entry_price is None:
            _issue(issues, "trade_ready_missing_entry", "TRADE_PLAN_READY requires entry_price.")
        if decision.stop_loss_plan.stop_price is None:
            _issue(issues, "trade_ready_missing_stop", "TRADE_PLAN_READY requires stop_price.")
        if not decision.target_plan.targets:
            _issue(issues, "trade_ready_missing_target", "TRADE_PLAN_READY requires at least one target.")
    else:
        if plan.show_trade_box:
            _issue(issues, "watch_chart_has_trade_box", "Non-trade states cannot show a trade box.")
        if plan.chart_template == "trade_plan_chart":
            _issue(issues, "watch_state_trade_chart", "Only TRADE_PLAN_READY may use trade_plan_chart.")
        if decision.entry_plan.entry_price is not None:
            _issue(issues, "watch_chart_has_entry", "Watch/review states cannot expose an executable entry price.")
        if decision.stop_loss_plan.stop_price is not None:
            _issue(issues, "watch_chart_has_stop", "Watch/review states cannot expose a stop loss.")
        if decision.target_plan.targets:
            _issue(issues, "watch_chart_has_target", "Watch/review states cannot expose take-profit targets.")


def _check_trade_ready_preconditions(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    if decision.official_state != "TRADE_PLAN_READY":
        return

    displacement = decision.displacement_assessment
    if displacement.direction not in {"bullish", "bearish"}:
        _issue(
            issues,
            "trade_ready_requires_valid_displacement",
            "TRADE_PLAN_READY requires a bullish or bearish displacement, not none/mixed.",
        )
    elif displacement.direction != decision.direction:
        _issue(
            issues,
            "trade_ready_requires_valid_displacement",
            "TRADE_PLAN_READY displacement direction must match the final trade direction.",
        )
    if displacement.quality not in {"clean", "strong"}:
        _issue(
            issues,
            "trade_ready_requires_valid_displacement",
            "TRADE_PLAN_READY requires clean or strong displacement quality.",
        )
    if not displacement.structure_broken:
        _issue(
            issues,
            "trade_ready_requires_valid_displacement",
            "TRADE_PLAN_READY requires displacement that actually broke structure.",
        )
    if not displacement.evidence_object_ids:
        _issue(
            issues,
            "trade_ready_requires_valid_displacement",
            "TRADE_PLAN_READY requires displacement evidence object IDs.",
        )

    thesis_text = str(decision.final_thesis or "").lower()
    contradiction_tokens = (
        "watch_only",
        "watch only",
        "no trade",
        "wait for",
        "refuses a trade plan",
        "does not have validated",
    )
    if any(token in thesis_text for token in contradiction_tokens):
        _issue(
            issues,
            "trade_ready_thesis_contradiction",
            "TRADE_PLAN_READY final_thesis cannot describe a watch/no-trade/refusal state.",
        )
    label_text = " ".join(
        str(label.text).lower()
        for label in decision.annotation_plan.labels
        if getattr(label, "text", None)
    )
    if any(token in label_text for token in contradiction_tokens):
        _issue(
            issues,
            "trade_ready_annotation_contradiction",
            "TRADE_PLAN_READY annotation labels cannot describe a watch/no-trade/refusal state.",
        )


def _check_active_range(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    active = decision.active_range
    if active.high is not None and active.low is not None and active.high <= active.low:
        _issue(issues, "active_range_invalid_bounds", "Active range high must be above active range low.")

    source_text = " ".join([str(active.source or ""), *[str(item) for item in active.evidence]]).lower()
    forbidden = (
        "ohlcv summary",
        "ohlcv_summary",
        "summary high",
        "summary low",
        "dataset high",
        "dataset low",
        "window high",
        "window low",
        "visible window extremes",
    )
    if any(token in source_text for token in forbidden):
        _issue(
            issues,
            "active_range_summary_source_forbidden",
            "Active range cannot be sourced from OHLCV summary highs/lows or visible-window extremes.",
        )

    authority = evidence_pack.get("active_range_authority")
    if not isinstance(authority, Mapping):
        return
    selected = authority.get("selected_range")
    if not isinstance(selected, Mapping):
        if active.high is not None or active.low is not None:
            _issue(
                issues,
                "active_range_claim_without_authority",
                "Decision claimed an active range even though active_range_authority was unresolved.",
            )
        return

    selected_high = _float(selected.get("range_high"))
    selected_low = _float(selected.get("range_low"))
    if selected_high is None or selected_low is None:
        _issue(issues, "active_range_authority_invalid", "Selected active range authority is missing range_high/range_low.")
        return
    if active.high is None or active.low is None:
        _issue(issues, "active_range_missing_selected_range", "Decision must carry the selected active range high/low.")
        return

    tolerance_high = max(abs(selected_high) * 0.0008, 1e-9)
    tolerance_low = max(abs(selected_low) * 0.0008, 1e-9)
    if abs(active.high - selected_high) > tolerance_high or abs(active.low - selected_low) > tolerance_low:
        _issue(
            issues,
            "active_range_mismatch_authority",
            "Decision active range does not match active_range_authority.selected_range.",
        )

    if active.source not in {"protected_swing_pair", "active_range_authority"}:
        _issue(
            issues,
            "active_range_source_not_structural",
            "Decision active range must declare source protected_swing_pair or active_range_authority.",
        )

    width_atr = active.width_atr if active.width_atr is not None else _float(selected.get("width_atr"))
    max_allowed = active.max_allowed_width_atr if active.max_allowed_width_atr is not None else _float(selected.get("max_width_atr"))
    if width_atr is not None and max_allowed is not None and width_atr > max_allowed + 1e-9:
        _issue(
            issues,
            "active_range_too_wide",
            f"Active range width {width_atr:.2f} ATR exceeds allowed maximum {max_allowed:.2f}.",
        )


def _check_direction_vs_active_range(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    authority = evidence_pack.get("active_range_authority")
    if not isinstance(authority, Mapping):
        return
    selected = authority.get("selected_range")
    if not isinstance(selected, Mapping):
        return
    range_direction = str(selected.get("direction") or "")
    if range_direction not in {"bullish", "bearish"}:
        return
    if decision.direction in {"bullish", "bearish"} and decision.direction != range_direction:
        _issue(
            issues,
            "direction_conflicts_with_active_range",
            (
                f"Decision direction '{decision.direction}' conflicts with active range direction "
                f"'{range_direction}'. This may be a valid retracement read, but it requires explicit justification."
            ),
            severity="warning",
        )


def _check_claimed_sweep(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    # Setup-dependent sweep rule: Reversal setups strictly require swept liquidity.
    setup_model = str(decision.setup_model or "").lower()
    is_reversal = "reversal" in setup_model or "choch" in setup_model
    if is_reversal and not decision.liquidity_story.swept_liquidity:
        _issue(issues, "reversal_requires_sweep", "Reversal/CHoCH setup model strictly requires swept liquidity.")

    if not decision.liquidity_story.swept_liquidity:
        return
    sweeps = _all_candidates(evidence_pack, ("sweeps",))
    if not sweeps:
        _issue(issues, "sweep_claim_without_candidate", "Decision claims swept liquidity but evidence pack has no sweep candidates.")
        return
    for claim in decision.liquidity_story.swept_liquidity:
        if not _candidate_matches_claim(sweeps, side=claim.side, price=claim.price, evidence_ids=claim.evidence_object_ids):
            _issue(issues, "sweep_claim_unmatched", f"Swept liquidity claim was not matched to candidate evidence: {claim.label or claim.price}.")


def _check_claimed_displacement(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    displacement = decision.displacement_assessment
    if displacement.quality in {"none", "weak"} and not displacement.structure_broken:
        return
    candidates = _all_candidates(evidence_pack, ("structure_breaks", "fvgs", "poi_grade_fvgs"))
    if not candidates:
        _issue(issues, "displacement_without_candidate", "Decision claims displacement but no structure/FVG candidate exists.")
        return
    if displacement.evidence_object_ids and not _ids_exist(candidates, displacement.evidence_object_ids):
        _issue(issues, "displacement_missing_evidence_id", "Displacement evidence IDs were not found in candidate evidence.")
    if displacement.direction in {"bullish", "bearish"}:
        directional = [item for item in candidates if str(item.get("direction", "")).lower() == displacement.direction]
        if not directional:
            _issue(issues, "displacement_direction_unmatched", "No candidate displacement evidence matches the claimed direction.")


def _check_active_poi(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    poi = decision.active_poi
    if poi.price_low is None and poi.price_high is None and not poi.poi_id:
        return
    candidates = _all_candidates(evidence_pack, ("order_blocks", "fvgs", "poi_grade_fvgs", "active_pois", "pois"))
    if not candidates:
        _issue(issues, "poi_without_candidate", "Active POI claim has no POI/order-block/FVG candidate evidence.")
        return
    if poi.evidence_object_ids and _ids_exist(candidates, poi.evidence_object_ids):
        return
    if poi.poi_id and _ids_exist(candidates, [poi.poi_id]):
        return
    if poi.price_low is not None and poi.price_high is not None:
        if any(_zones_overlap(poi.price_low, poi.price_high, candidate) for candidate in candidates):
            return
    _issue(issues, "poi_claim_unmatched", "Active POI price/id did not match candidate evidence.")


def _check_structural_stop(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    if decision.official_state != "TRADE_PLAN_READY":
        return
    stop = decision.stop_loss_plan.stop_price
    invalidation = decision.invalidation.invalidation_price
    entry = decision.entry_plan.entry_price
    if stop is None or invalidation is None or entry is None:
        return
    if abs(stop - invalidation) > max(abs(invalidation) * 0.0005, 1e-9):
        _issue(issues, "stop_not_structural_invalidation", "Stop loss must equal the structural invalidation level.")
    poi = decision.active_poi
    if decision.direction == "bearish":
        if stop <= entry:
            _issue(issues, "bearish_stop_not_above_entry", "Bearish structural stop must be above entry.")
        if poi.price_high is not None and stop < poi.price_high:
            _issue(issues, "bearish_stop_inside_poi", "Bearish structural stop must protect above the POI high.")
    if decision.direction == "bullish":
        if stop >= entry:
            _issue(issues, "bullish_stop_not_below_entry", "Bullish structural stop must be below entry.")
        if poi.price_low is not None and stop > poi.price_low:
            _issue(issues, "bullish_stop_inside_poi", "Bullish structural stop must protect below the POI low.")


def _check_target_logic(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    if decision.official_state != "TRADE_PLAN_READY":
        return
    entry = decision.entry_plan.entry_price
    if entry is None:
        return
    targets = decision.target_plan.targets
    liquidity_candidates = _all_candidates(evidence_pack, ("liquidity_levels",))
    for target in targets:
        if decision.direction == "bearish" and target.price >= entry:
            _issue(issues, "bearish_target_above_entry", "Bearish model-completion target must be below entry.")
        if decision.direction == "bullish" and target.price <= entry:
            _issue(issues, "bullish_target_below_entry", "Bullish model-completion target must be above entry.")
        matched = False
        if target.evidence_object_ids and _ids_exist(liquidity_candidates, target.evidence_object_ids):
            matched = True
        if not matched and _price_in_candidates(target.price, liquidity_candidates):
            matched = True
        if not matched and _target_matches_active_range(decision, target.price):
            matched = True
        if not matched:
            _issue(issues, "target_not_model_completion_liquidity", "Target must match model-completion liquidity evidence.")


def _check_rr(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    if decision.official_state != "TRADE_PLAN_READY":
        return
    entry = decision.entry_plan.entry_price
    stop = decision.stop_loss_plan.stop_price
    if entry is None or stop is None or not decision.target_plan.targets:
        return
    risk = abs(entry - stop)
    if risk <= 0:
        _issue(issues, "rr_zero_risk", "RR cannot be computed with zero risk.")
        return
    best_rr = max(abs(entry - target.price) / risk for target in decision.target_plan.targets)
    claimed_rr = decision.rr_status.rr if decision.rr_status.rr is not None else best_rr
    if best_rr + 1e-9 < MINIMUM_RR or claimed_rr + 1e-9 < MINIMUM_RR or not decision.rr_status.pass_rr:
        _issue(issues, "rr_below_minimum", "TRADE_PLAN_READY requires RR >= 3.0.")


def _check_label_budget(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    template = decision.annotation_plan.chart_template
    limits = {"context_chart": 5, "watch_chart": 7, "review_chart": 7, "trade_plan_chart": 8, "debug_chart": 99}
    limit = limits.get(template, 7)
    if len(decision.annotation_plan.labels) > limit:
        _issue(issues, "annotation_label_budget_exceeded", f"{template} allows at most {limit} official labels.")


def _check_self_review(decision: AISMCDecision, issues: list[ValidationIssue]) -> None:
    review = decision.self_review
    failed = []
    for field_name in ("active_range_check", "poi_check", "annotation_check", "refusal_check"):
        if getattr(review, field_name) == "failed":
            failed.append(field_name)
    if failed:
        _issue(
            issues,
            "ai_self_review_failed",
            f"AI self-review failed: {', '.join(failed)}.",
        )
    if decision.official_state == "TRADE_PLAN_READY":
        not_passed = [
            field_name
            for field_name in ("active_range_check", "poi_check", "annotation_check", "refusal_check")
            if getattr(review, field_name) != "passed"
        ]
        if not_passed:
            _issue(
                issues,
                "trade_ready_requires_completed_self_review",
                f"TRADE_PLAN_READY requires completed self-review checks: {', '.join(not_passed)}.",
            )


def _all_candidates(evidence_pack: Mapping[str, Any], groups: Sequence[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_tf = evidence_pack.get("detector_candidates") or {}
    if not isinstance(by_tf, Mapping):
        return result
    for tf_payload in by_tf.values():
        if not isinstance(tf_payload, Mapping):
            continue
        for group in groups:
            for item in tf_payload.get(group, []) or []:
                if isinstance(item, Mapping):
                    result.append(dict(item))
    return result


def _candidate_matches_claim(
    candidates: list[dict[str, Any]],
    *,
    side: str | None,
    price: float | None,
    evidence_ids: Sequence[str],
) -> bool:
    if evidence_ids and _ids_exist(candidates, evidence_ids):
        return True
    for candidate in candidates:
        if side not in {None, "", "unknown"}:
            candidate_side = _candidate_side(candidate)
            if candidate_side and candidate_side != side:
                continue
        if price is None:
            return True
        if _candidate_price_matches(candidate, price):
            return True
    return False


def _ids_exist(candidates: list[dict[str, Any]], evidence_ids: Sequence[str]) -> bool:
    available = set()
    for item in candidates:
        for key in ("object_id", "id", "liquidity_id", "poi_id"):
            if item.get(key) is not None:
                available.add(str(item.get(key)))
    return all(str(evidence_id) in available for evidence_id in evidence_ids)


def _candidate_side(candidate: Mapping[str, Any]) -> str | None:
    side = candidate.get("side")
    if not side and isinstance(candidate.get("evidence"), Mapping):
        side = candidate["evidence"].get("side") or candidate["evidence"].get("liquidity_side")
    return str(side).lower() if side else None


def _candidate_price_matches(candidate: Mapping[str, Any], price: float, tolerance_bps: float = 8.0) -> bool:
    candidate_prices = []
    for key in ("price", "swept_price", "level_price", "price_low", "price_high"):
        value = candidate.get(key)
        if value is not None:
            candidate_prices.append(_float(value))
    evidence = candidate.get("evidence")
    if isinstance(evidence, Mapping):
        for key in ("swept_price", "broken_price", "price", "level_price"):
            value = evidence.get(key)
            if value is not None:
                candidate_prices.append(_float(value))
    candidate_prices = [value for value in candidate_prices if value is not None]
    tolerance = max(abs(price) * tolerance_bps / 10000.0, 1e-9)
    return any(abs(value - price) <= tolerance for value in candidate_prices)


def _price_in_candidates(price: float, candidates: list[dict[str, Any]]) -> bool:
    return any(_candidate_price_matches(candidate, price) for candidate in candidates)


def _zones_overlap(price_low: float, price_high: float, candidate: Mapping[str, Any]) -> bool:
    low = _float(candidate.get("price_low"))
    high = _float(candidate.get("price_high"))
    if low is None or high is None:
        return False
    cand_low, cand_high = sorted([low, high])
    claim_low, claim_high = sorted([price_low, price_high])
    return max(cand_low, claim_low) <= min(cand_high, claim_high)


def _target_matches_active_range(decision: AISMCDecision, target_price: float) -> bool:
    range_low = decision.active_range.low
    range_high = decision.active_range.high
    if decision.direction == "bearish" and range_low is not None:
        return abs(target_price - range_low) <= max(abs(range_low) * 0.0008, 1e-9)
    if decision.direction == "bullish" and range_high is not None:
        return abs(target_price - range_high) <= max(abs(range_high) * 0.0008, 1e-9)
    return False


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_anchor_price(anchor: str, evidence_ids: list[str], evidence_pack: Mapping[str, Any], decision: AISMCDecision, kind: str) -> float | None:
    anchor = str(anchor or "").lower()
    
    # 1. Search by exact evidence ID match
    candidates = []
    det_candidates = (evidence_pack.get("detector_candidates") or {})
    for tf, tf_data in det_candidates.items():
        if isinstance(tf_data, Mapping):
            for group, group_items in tf_data.items():
                if isinstance(group_items, list):
                    for item in group_items:
                        if isinstance(item, Mapping) and item.get("object_id") in evidence_ids:
                            candidates.append(item)
                            
    # Also check active range authority
    selected_range = None
    ara = evidence_pack.get("active_range_authority") or {}
    if isinstance(ara, Mapping):
        selected_range = ara.get("selected_range")
        
    # Resolve based on candidate match
    if candidates:
        first = candidates[0]
        # Depending on kind, extract price
        if kind == "entry":
            if "price_low" in first and "price_high" in first:
                return (float(first["price_low"]) + float(first["price_high"])) / 2.0
            return float(first.get("price") or first.get("price_low") or first.get("price_high") or 0.0)
        elif kind == "stop":
            if "price_high" in first and "above" in anchor:
                return float(first["price_high"])
            if "price_low" in first and "below" in anchor:
                return float(first["price_low"])
            return float(first.get("price") or first.get("price_high") or first.get("price_low") or 0.0)
        elif kind == "target":
            return float(first.get("price") or first.get("price_low") or first.get("price_high") or 0.0)
        elif kind == "invalidation":
            if "price_high" in first and "above" in anchor:
                return float(first["price_high"])
            if "price_low" in first and "below" in anchor:
                return float(first["price_low"])
            return float(first.get("price") or first.get("price_high") or first.get("price_low") or 0.0)

    # 2. Semantic text fallback matching
    active_range = decision.active_range
    selected_high = float(active_range.high) if active_range.high is not None else (float(selected_range.get("range_high")) if selected_range else None)
    selected_low = float(active_range.low) if active_range.low is not None else (float(selected_range.get("range_low")) if selected_range else None)

    if "range_high" in anchor or "structural_high" in anchor:
        return selected_high
    if "range_low" in anchor or "structural_low" in anchor:
        return selected_low

    if "sweep_high" in anchor or "above_sweep" in anchor:
        sweeps = []
        for tf, tf_data in det_candidates.items():
            if isinstance(tf_data, Mapping):
                sweeps.extend(tf_data.get("sweeps", []))
        prices = [float(s["price"]) for s in sweeps if "price" in s]
        return max(prices) if prices else selected_high

    if "sweep_low" in anchor or "below_sweep" in anchor:
        sweeps = []
        for tf, tf_data in det_candidates.items():
            if isinstance(tf_data, Mapping):
                sweeps.extend(tf_data.get("sweeps", []))
        prices = [float(s["price"]) for s in sweeps if "price" in s]
        return min(prices) if prices else selected_low

    if "fvg" in anchor or "poi" in anchor or "ob" in anchor:
        poi = decision.active_poi
        if poi.price_high is not None and poi.price_low is not None:
            if decision.direction == "bullish":
                return float(poi.price_low)
            else:
                return float(poi.price_high)

    return None


def _check_anchors_and_grounding(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> dict[str, Any]:
    mapped_prices = {
        "entry": None,
        "stop": None,
        "targets": [],
        "invalidation": None
    }
    
    # 1. Entry Anchor
    entry = decision.entry_plan
    if entry.entry_ready:
        if not entry.entry_anchor:
            _issue(issues, "entry_anchor_missing", "Entry plan is ready but entry_anchor is missing.")
        else:
            resolved = _resolve_anchor_price(entry.entry_anchor, entry.evidence_object_ids, evidence_pack, decision, "entry")
            if resolved is None:
                _issue(issues, "entry_anchor_unresolved", f"Could not resolve entry_anchor '{entry.entry_anchor}' to any candidate.")
            else:
                mapped_prices["entry"] = resolved
                if entry.entry_price is not None:
                    tolerance = max(resolved * 0.001, 1e-5)
                    if abs(entry.entry_price - resolved) > tolerance:
                        _issue(
                            issues,
                            "entry_price_grounding_mismatch",
                            f"Proposed entry price {entry.entry_price} does not match resolved anchor price {resolved}."
                        )
                        
    # 2. Stop Anchor
    stop = decision.stop_loss_plan
    if entry.entry_ready:
        if not stop.stop_anchor:
            _issue(issues, "stop_anchor_missing", "Trade plan is ready but stop_anchor is missing.")
        else:
            resolved = _resolve_anchor_price(stop.stop_anchor, stop.evidence_object_ids, evidence_pack, decision, "stop")
            if resolved is None:
                _issue(issues, "stop_anchor_unresolved", f"Could not resolve stop_anchor '{stop.stop_anchor}' to any candidate.")
            else:
                mapped_prices["stop"] = resolved
                if stop.stop_price is not None:
                    tolerance = max(resolved * 0.001, 1e-5)
                    if abs(stop.stop_price - resolved) > tolerance:
                        _issue(
                            issues,
                            "stop_price_grounding_mismatch",
                            f"Proposed stop price {stop.stop_price} does not match resolved anchor price {resolved}."
                        )

    # 3. Targets Anchor
    targets = decision.target_plan.targets
    if entry.entry_ready and targets:
        for idx, t in enumerate(targets):
            if not t.target_anchor:
                _issue(issues, "target_anchor_missing", f"Target {idx} is missing target_anchor.")
            else:
                resolved = _resolve_anchor_price(t.target_anchor, t.evidence_object_ids, evidence_pack, decision, "target")
                if resolved is None:
                    _issue(issues, "target_anchor_unresolved", f"Could not resolve target_anchor '{t.target_anchor}' for target {idx}.")
                else:
                    mapped_prices["targets"].append(resolved)
                    if t.price is not None:
                        tolerance = max(resolved * 0.001, 1e-5)
                        if abs(t.price - resolved) > tolerance:
                            _issue(
                                issues,
                                "target_price_grounding_mismatch",
                                f"Proposed target price {t.price} does not match resolved anchor price {resolved}."
                            )

    # 4. Invalidation Anchor
    inval = decision.invalidation
    if inval.invalidation_anchor:
        resolved = _resolve_anchor_price(inval.invalidation_anchor, inval.evidence_object_ids, evidence_pack, decision, "invalidation")
        if resolved is None:
            _issue(issues, "invalidation_anchor_unresolved", f"Could not resolve invalidation_anchor '{inval.invalidation_anchor}'.")
        else:
            mapped_prices["invalidation"] = resolved
            if inval.invalidation_price is not None:
                tolerance = max(resolved * 0.001, 1e-5)
                if abs(inval.invalidation_price - resolved) > tolerance:
                    _issue(
                        issues,
                        "invalidation_price_grounding_mismatch",
                        f"Proposed invalidation price {inval.invalidation_price} does not match resolved anchor price {resolved}."
                    )
                    
    return mapped_prices


def _check_liquidity_status(decision: AISMCDecision, evidence_pack: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    swept_prices = {float(liq.price) for liq in decision.liquidity_story.swept_liquidity if liq.price is not None}
    
    det_candidates = (evidence_pack.get("detector_candidates") or {})
    for tf, tf_data in det_candidates.items():
        if isinstance(tf_data, Mapping):
            for sweep in tf_data.get("sweeps", []):
                if "price" in sweep:
                    swept_prices.add(float(sweep["price"]))
                    
    all_refs = [
        *decision.liquidity_story.obvious_liquidity,
        *decision.liquidity_story.unswept_liquidity
    ]
    for ref in all_refs:
        if ref.status == "fresh_untaken_liquidity" and ref.price is not None:
            for sp in swept_prices:
                if abs(float(ref.price) - sp) < (sp * 0.0005):
                    _issue(
                        issues,
                        "swept_low_classified_as_fresh_ssl",
                        f"Liquidity at {ref.price} classified as fresh_untaken_liquidity, but it was already swept."
                    )
