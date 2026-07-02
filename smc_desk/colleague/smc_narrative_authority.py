"""Final SMC narrative authority.

This module is intentionally downstream of detectors and watch-state logic. It
does not discover new SMC objects. It arbitrates the final trader-facing story:
which model matters, which POI is official, what must happen next, and whether
a trade box is allowed.
"""
from __future__ import annotations

from typing import Any, Mapping

from smc_desk.decision.entry_style_selector import select_entry_style
from smc_desk.decision.hybrid_stop_selector import select_hybrid_structural_stop
from smc_desk.decision.liquidity_target_selector import select_liquidity_targets
from smc_desk.decision.setup_classifier import NO_CLEAR_MODEL, classify_setup_model
from smc_desk.decision.trade_rejection_engine import evaluate_trade_rejections
from smc_desk.profile.smc_intraday_profile import SMC_INTRADAY_PROFILE, assert_intraday_profile_contract


TRADE_PLAN_READY = "TRADE_PLAN_READY"
WATCH_ONLY = "WATCH_ONLY"


def build_smc_narrative_authority(
    *,
    symbol: str,
    cognitive_result: Mapping[str, Any],
    visual_reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assert_intraday_profile_contract()
    watch = _mapping(cognitive_result.get("watch_state"))
    readiness = _mapping(cognitive_result.get("execution_readiness"))
    move = _mapping(cognitive_result.get("inducement_continuation"))
    refusal = _mapping(cognitive_result.get("refusal"))
    hierarchy = _mapping(cognitive_result.get("structure_hierarchy"))
    liquidity_sequence = _mapping(cognitive_result.get("liquidity_sequence"))
    visual_reconciliation = _mapping(visual_reconciliation)

    active_poi = _mapping(watch.get("active_poi"))
    official_bias = _official_bias(watch, hierarchy)
    official_state = _official_state(watch, readiness, move, refusal, visual_reconciliation)
    trade_plan_ready = _trade_plan_ready(cognitive_result, watch, readiness, official_state)
    official_trade_plan_state = TRADE_PLAN_READY if trade_plan_ready else WATCH_ONLY
    chart_template = "trade_plan_chart" if trade_plan_ready else ("review_chart" if official_state == "REVIEW_REQUIRED" else "watch_chart")
    official_active_poi = _official_active_poi(active_poi)
    setup_classification_obj = classify_setup_model(
        cognitive_result=cognitive_result,
        official_bias=official_bias,
        active_poi=active_poi,
        structure_hierarchy=hierarchy,
        liquidity_sequence=liquidity_sequence,
        inducement_continuation=move,
    )
    setup_classification = setup_classification_obj.to_dict()
    official_model = _official_model(official_bias, official_state, setup_classification)
    continuation = [str(item) for item in move.get("continuation_confirmed_if", []) or []]
    inducement = [str(item) for item in move.get("inducement_confirmed_if", []) or []]
    invalidation = _watch_invalidation(official_bias, active_poi)
    target_selection = select_liquidity_targets(
        setup_model=setup_classification,
        structure_hierarchy=hierarchy,
        active_poi=active_poi,
        current_price=_current_price(cognitive_result),
        invalidation=invalidation,
        entry_timeframe=str(SMC_INTRADAY_PROFILE["default_entry_timeframe"]),
    )
    fallback_liquidity_draw = _liquidity_draw(
        direction=official_bias,
        active_poi=active_poi,
        hierarchy=hierarchy,
        liquidity_sequence=liquidity_sequence,
    )
    liquidity_draw = _official_liquidity_draw(target_selection, fallback_liquidity_draw)
    stop_selection = select_hybrid_structural_stop(
        direction=official_bias,
        entry_style="aggressive",
        active_poi=active_poi,
        protected_extreme=_protected_extreme(official_bias, hierarchy),
    )
    entry_style = select_entry_style(
        active_poi=active_poi,
        displacement=_displacement_summary(official_bias, move),
        liquidity_sweep=_has_directional_sweep(official_bias, liquidity_sequence),
        rr=None,
        poi_width_pct=_poi_width_pct(active_poi),
        inducement_risk=str(move.get("state") or "") in {"POSSIBLE_INDUCEMENT", "INDUCEMENT_CONFIRMED"},
    )
    rr_validation = {
        "status": "NOT_EVALUATED_WATCH_ONLY",
        "rr": None,
        "minimum_rr": float(SMC_INTRADAY_PROFILE["minimum_rr"]),
        "reasons": ["RR can only become official after entry, structural stop, and setup target are ready."],
    }
    trade_rejection = evaluate_trade_rejections(
        setup_model=setup_classification,
        htf_control=official_state != "REVIEW_REQUIRED",
        liquidity_sweep=_has_directional_sweep(official_bias, liquidity_sequence),
        displacement=_displacement_summary(official_bias, move),
        active_poi=active_poi,
        move_state=str(move.get("state") or ""),
        target_selection=target_selection,
        rr_validation=rr_validation,
        entry_style=entry_style,
        watch_state=official_state,
    )
    confirmation_needed = _confirmation_needed(
        official_bias=official_bias,
        active_poi=official_active_poi,
        continuation=continuation,
        official_state=official_state,
    )
    reasoning_steps = _reasoning_steps(
        official_bias=official_bias,
        official_state=official_state,
        official_active_poi=official_active_poi,
        liquidity_draw=liquidity_draw,
        invalidation=invalidation,
        confirmation_needed=confirmation_needed,
        watch=watch,
        readiness=readiness,
        move=move,
        hierarchy=hierarchy,
        setup_classification=setup_classification,
        target_selection=target_selection,
    )

    return {
        "schema": "smc_narrative_authority_v2",
        "symbol": symbol,
        "official_model": official_model,
        "official_setup_model": setup_classification.get("setup_type"),
        "official_bias": official_bias,
        "official_state": official_state,
        "setup_timeframe": setup_classification.get("setup_timeframe"),
        "entry_timeframe": entry_style.get("entry_timeframe"),
        "refinement_timeframe": entry_style.get("refinement_timeframe"),
        "liquidity_taken": _liquidity_taken(liquidity_sequence, official_bias),
        "displacement": _displacement_summary(official_bias, move),
        "official_active_poi": official_active_poi,
        "active_poi": official_active_poi,
        "official_liquidity_draw": liquidity_draw,
        "official_invalidation": invalidation,
        "invalidation": invalidation,
        "official_confirmation_needed": confirmation_needed,
        "confirmation_needed": _confirmation_steps(confirmation_needed, continuation, entry_style),
        "official_trade_plan_state": official_trade_plan_state,
        "trade_plan_state": official_trade_plan_state,
        "entry_status": _entry_status(official_state, entry_style),
        "chart_template": chart_template,
        "show_trade_box": trade_plan_ready,
        "entry": None,
        "stop_loss": None,
        "take_profit": [],
        "targets": [],
        "liquidity_targets": target_selection.get("targets", []),
        "rr": None,
        "minimum_rr": float(SMC_INTRADAY_PROFILE["minimum_rr"]),
        "setup_classification": setup_classification,
        "target_selection": target_selection,
        "stop_selection": stop_selection,
        "entry_style": entry_style,
        "rr_validation": rr_validation,
        "trade_rejection": trade_rejection,
        "continuation_confirmed_if": continuation,
        "inducement_confirmed_if": inducement,
        "reasoning_steps": reasoning_steps,
        "debug_sources": {
            "watch_state": watch.get("final_state"),
            "execution_readiness": readiness.get("state"),
            "inducement_continuation": move.get("state"),
            "final_action": cognitive_result.get("final_action") or refusal.get("final_action"),
            "visual_reconciliation": visual_reconciliation.get("status"),
        },
        "doctrine_profile": dict(SMC_INTRADAY_PROFILE),
        "authority_contract": {
            "detectors_are_inputs_not_final_story": True,
            "watch_states_are_not_trade_plans": not trade_plan_ready,
            "no_trade_box_before_trade_plan_ready": True,
            "minimum_rr": float(SMC_INTRADAY_PROFILE["minimum_rr"]),
            "risk_authority": SMC_INTRADAY_PROFILE["risk_authority"],
            "position_sizing": SMC_INTRADAY_PROFILE["position_sizing"],
            "leverage_decision": SMC_INTRADAY_PROFILE["leverage_decision"],
            "account_risk_decision": SMC_INTRADAY_PROFILE["account_risk_decision"],
            "partial_close_rules": SMC_INTRADAY_PROFILE["partial_close_rules"],
            "breakeven_rules": SMC_INTRADAY_PROFILE["breakeven_rules"],
            "trailing_rules": SMC_INTRADAY_PROFILE["trailing_rules"],
            "paper_execution": "disabled",
            "live_execution": "disabled",
            "capital_risk": 0,
        },
    }


def assert_narrative_authority_contract(authority: Mapping[str, Any]) -> None:
    if not authority.get("official_model"):
        raise AssertionError("Narrative authority missing official_model.")
    if not authority.get("official_state"):
        raise AssertionError("Narrative authority missing official_state.")
    if authority.get("official_trade_plan_state") != TRADE_PLAN_READY:
        if authority.get("show_trade_box"):
            raise AssertionError("Watch-only narrative must not show a trade box.")
        if authority.get("entry") is not None or authority.get("stop_loss") is not None:
            raise AssertionError("Watch-only narrative must not expose executable entry/stop.")
        if authority.get("take_profit") or authority.get("targets"):
            raise AssertionError("Watch-only narrative must not expose take-profit trade-plan levels.")
    if authority.get("show_trade_box") and authority.get("chart_template") != "trade_plan_chart":
        raise AssertionError("Only trade-plan charts may show a trade box.")
    contract = _mapping(authority.get("authority_contract"))
    if contract.get("risk_authority") != "user_only":
        raise AssertionError("Narrative authority must not own account-risk decisions.")
    if float(contract.get("minimum_rr", 0.0)) != 3.0:
        raise AssertionError("Narrative authority minimum RR must remain 3.0.")


def _official_state(
    watch: Mapping[str, Any],
    readiness: Mapping[str, Any],
    move: Mapping[str, Any],
    refusal: Mapping[str, Any],
    visual: Mapping[str, Any],
) -> str:
    visual_status = str(visual.get("status") or "")
    if visual_status in {"VISUAL_CONTEXT_MISMATCH", "VISUAL_CONTEXT_UNVERIFIED"}:
        return "REVIEW_REQUIRED"
    watch_state = str(watch.get("final_state") or "")
    readiness_state = str(readiness.get("state") or "")
    move_state = str(move.get("state") or "")
    if watch_state in {"REVIEW_REQUIRED", "REVIEW_REQUIRED_POI_OUTSIDE_PROTECTED_RANGE", "NO_TRADE_HTF_CONFLICT"}:
        return "REVIEW_REQUIRED"
    if readiness_state == "MOVE_STARTED_NOT_CHASEABLE" or move_state == "MOVE_STARTED_NOT_CHASEABLE":
        return "MOVE_STARTED_NOT_CHASEABLE"
    if readiness_state == "WAIT_FOR_RETRACE_TO_LTF_SUPPLY" or watch_state == "WATCH_BEARISH_RETRACE_TO_SUPPLY":
        return "WAIT_FOR_RETRACE_TO_SUPPLY"
    if watch_state == "WATCH_BULLISH_RETRACE_TO_DEMAND":
        return "WAIT_FOR_RETRACE_TO_DEMAND"
    if readiness_state == "POI_REACHED_AWAIT_CONFIRMATION" or watch_state == "POI_TOUCHED_AWAIT_15M_CONFIRMATION":
        return "POI_TOUCHED_AWAIT_CONFIRMATION"
    if move_state in {"POSSIBLE_INDUCEMENT", "INDUCEMENT_CONFIRMED"} or readiness_state == "INDUCEMENT_RISK_HIGH":
        return "POSSIBLE_INDUCEMENT"
    if move_state == "CONTINUATION_CONFIRMED":
        return "CONTINUATION_CONFIRMED_OBSERVE_ONLY"
    if readiness_state == "EARLY_CONFIRMATION_FORMING":
        return "EARLY_CONFIRMATION_FORMING"
    if str(refusal.get("final_action") or "") in {"REFUSE_PERCEPTION", "SOURCE_MISMATCH"}:
        return "REVIEW_REQUIRED"
    if watch_state:
        return "WATCH_ONLY"
    return "THESIS_ONLY"


def _trade_plan_ready(
    cognitive_result: Mapping[str, Any],
    watch: Mapping[str, Any],
    readiness: Mapping[str, Any],
    official_state: str,
) -> bool:
    return (
        official_state == TRADE_PLAN_READY
        and bool(watch.get("signal_allowed"))
        and bool(cognitive_result.get("signal_allowed"))
        and str(readiness.get("state") or "") == TRADE_PLAN_READY
        and str(cognitive_result.get("final_action") or "").upper() in {"EXECUTE", "SIGNAL"}
    )


def _official_bias(watch: Mapping[str, Any], hierarchy: Mapping[str, Any]) -> str:
    direction = str(watch.get("direction") or "").lower()
    if direction in {"bullish", "bearish"}:
        return direction
    for tf in ("4h", "1h", "15m", "1d"):
        item = _mapping(hierarchy.get(tf))
        bias = str(item.get("external_bias") or "").lower()
        if bias in {"bullish", "bearish"}:
            return bias
    return "neutral"


def _official_model(bias: str, state: str, setup_classification: Mapping[str, Any]) -> str:
    if state == "REVIEW_REQUIRED":
        return "review_required"
    if bias not in {"bullish", "bearish"}:
        return "thesis_only"
    if state in {"WAIT_FOR_RETRACE_TO_SUPPLY", "WAIT_FOR_RETRACE_TO_DEMAND", "POI_TOUCHED_AWAIT_CONFIRMATION", "MOVE_STARTED_NOT_CHASEABLE", "CONTINUATION_CONFIRMED_OBSERVE_ONLY"}:
        return f"{bias}_continuation_watch"
    if state == "POSSIBLE_INDUCEMENT":
        return f"{bias}_inducement_risk_watch"
    return f"{bias}_observe_only"


def _official_active_poi(active_poi: Mapping[str, Any]) -> dict[str, Any] | None:
    if not active_poi:
        return None
    low = active_poi.get("price_low")
    high = active_poi.get("price_high")
    if low in {None, ""} or high in {None, ""}:
        return None
    timeframe = str(active_poi.get("timeframe") or "")
    kind = str(active_poi.get("kind") or "POI")
    return {
        "poi_id": active_poi.get("poi_id"),
        "timeframe": timeframe,
        "kind": kind,
        "direction": active_poi.get("direction"),
        "price_low": low,
        "price_high": high,
        "zone_label": f"{timeframe} {kind} {low}-{high}".strip(),
        "freshness": active_poi.get("freshness"),
        "price_relation": active_poi.get("price_relation"),
        "validity_status": active_poi.get("validity_status"),
        "selection_score": active_poi.get("selection_score"),
    }


def _watch_invalidation(direction: str, active_poi: Mapping[str, Any]) -> dict[str, Any] | None:
    if not active_poi:
        return None
    if direction == "bearish":
        price = active_poi.get("price_high")
        return None if price in {None, ""} else {
            "type": "watch_invalidation_not_stop_loss",
            "price": price,
            "condition": f"reclaim/accept above {price}",
            "source": "active_poi_high",
        }
    if direction == "bullish":
        price = active_poi.get("price_low")
        return None if price in {None, ""} else {
            "type": "watch_invalidation_not_stop_loss",
            "price": price,
            "condition": f"reclaim/accept below {price}",
            "source": "active_poi_low",
        }
    return None


def _liquidity_draw(
    *,
    direction: str,
    active_poi: Mapping[str, Any],
    hierarchy: Mapping[str, Any],
    liquidity_sequence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    draws: list[dict[str, Any]] = []
    for tf in ("15m", "1h", "4h", "1d"):
        sequence = _mapping(liquidity_sequence.get(tf))
        draw = sequence.get("current_liquidity_draw")
        if draw:
            draws.append({"timeframe": tf, "label": str(draw), "source": "liquidity_sequence"})
    candidate_tfs = []
    if active_poi.get("timeframe"):
        candidate_tfs.append(str(active_poi.get("timeframe")))
    candidate_tfs.extend(["15m", "1h", "4h"])
    for tf in candidate_tfs:
        item = _mapping(hierarchy.get(tf))
        dr = _mapping(item.get("dealing_range"))
        if direction == "bearish":
            price = item.get("external_range_low") or item.get("protected_low") or dr.get("range_low")
            label = "sell-side liquidity"
        elif direction == "bullish":
            price = item.get("external_range_high") or item.get("protected_high") or dr.get("range_high")
            label = "buy-side liquidity"
        else:
            price = None
            label = "liquidity"
        if price not in {None, ""}:
            draws.append({"timeframe": tf, "price": price, "label": label, "source": "active_external_range"})
    return _unique_draws(draws)[:4]


def _official_liquidity_draw(target_selection: Mapping[str, Any], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    draws: list[dict[str, Any]] = []
    for target in target_selection.get("targets", []) or []:
        if target.get("price") in {None, ""}:
            continue
        draws.append({
            "timeframe": target.get("timeframe"),
            "price": target.get("price"),
            "label": target.get("reason") or "setup liquidity target",
            "source": target.get("source") or "setup_dependent_liquidity",
            "not_take_profit": True,
        })
    draws.extend(dict(item) for item in fallback)
    return _unique_draws(draws)[:4]


def _confirmation_needed(
    *,
    official_bias: str,
    active_poi: Mapping[str, Any] | None,
    continuation: list[str],
    official_state: str,
) -> dict[str, Any]:
    if official_state == "MOVE_STARTED_NOT_CHASEABLE":
        summary = "Do not chase; wait for retracement into the official watch zone and rejection."
    elif continuation:
        summary = "; ".join(continuation[:3])
    elif active_poi and official_bias == "bearish":
        summary = "Wait for bearish 15m confirmation from the official supply zone."
    elif active_poi and official_bias == "bullish":
        summary = "Wait for bullish 15m confirmation from the official demand zone."
    else:
        summary = "Wait for a cleaner protected-range POI and confirmation sequence."
    return {
        "summary": summary,
        "requires_15m_confirmation": official_bias in {"bullish", "bearish"},
        "trade_plan_ready": False,
    }


def _reasoning_steps(
    *,
    official_bias: str,
    official_state: str,
    official_active_poi: Mapping[str, Any] | None,
    liquidity_draw: list[Mapping[str, Any]],
    invalidation: Mapping[str, Any] | None,
    confirmation_needed: Mapping[str, Any],
    watch: Mapping[str, Any],
    readiness: Mapping[str, Any],
    move: Mapping[str, Any],
    hierarchy: Mapping[str, Any],
    setup_classification: Mapping[str, Any],
    target_selection: Mapping[str, Any],
) -> list[str]:
    steps = [
        f"HTF/model bias is {official_bias}.",
        f"Active setup model is {setup_classification.get('setup_type')}.",
        _liquidity_taken_step(hierarchy),
        f"Move-quality state is {move.get('state', 'unknown')}.",
    ]
    if official_active_poi:
        steps.append(f"Official POI is {official_active_poi.get('zone_label')}.")
    else:
        steps.append("No official active POI is certified.")
    steps.extend([
        f"Official state is {official_state}; execution-readiness is {readiness.get('state', 'unknown')}.",
        f"Confirmation needed: {confirmation_needed.get('summary')}",
    ])
    if invalidation:
        steps.append(f"Watch invalidation: {invalidation.get('condition')} (not an executable stop loss).")
    if liquidity_draw:
        steps.append("Liquidity draw to monitor: " + ", ".join(_draw_text(item) for item in liquidity_draw[:3]) + ".")
    if target_selection.get("status"):
        steps.append(f"Setup-dependent target status: {target_selection.get('status')}.")
    reasons = [str(item) for item in watch.get("reasons", []) or []]
    if reasons:
        steps.append("Watch-state reason: " + reasons[0])
    steps.append("Trade box remains disabled until the narrative authority emits TRADE_PLAN_READY.")
    return steps


def _liquidity_taken_step(hierarchy: Mapping[str, Any]) -> str:
    ids = []
    for tf in ("4h", "1h", "15m"):
        item = _mapping(hierarchy.get(tf))
        if item.get("latest_external_break_id"):
            ids.append(f"{tf}:{item.get('latest_external_break_id')}")
    return "Liquidity/structure evidence: " + (", ".join(ids[-3:]) if ids else "no decisive external break recorded.")


def _draw_text(item: Mapping[str, Any]) -> str:
    if item.get("price") not in {None, ""}:
        return f"{item.get('timeframe')} {item.get('label')} {item.get('price')}"
    return str(item.get("label") or item.get("source") or "liquidity")


def _current_price(cognitive_result: Mapping[str, Any]) -> Any:
    perception = _mapping(cognitive_result.get("perception_by_tf"))
    for tf in ("15m", "1h", "4h"):
        snapshot = _mapping(perception.get(tf))
        if snapshot.get("last_price") not in {None, ""}:
            return snapshot.get("last_price")
    return cognitive_result.get("last_price")


def _protected_extreme(direction: str, hierarchy: Mapping[str, Any]) -> Any:
    for tf in ("1h", "4h", "15m"):
        item = _mapping(hierarchy.get(tf))
        if direction == "bearish" and item.get("protected_high") not in {None, ""}:
            return item.get("protected_high")
        if direction == "bullish" and item.get("protected_low") not in {None, ""}:
            return item.get("protected_low")
    return None


def _poi_width_pct(active_poi: Mapping[str, Any]) -> float | None:
    try:
        low = float(active_poi.get("price_low"))
        high = float(active_poi.get("price_high"))
        mid = max(abs((low + high) / 2), 1e-12)
        return abs(high - low) / mid * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _has_directional_sweep(direction: str, liquidity_sequence: Mapping[str, Any]) -> bool:
    for tf in ("15m", "1h", "4h", "1d"):
        sequence = _mapping(liquidity_sequence.get(tf))
        if direction == "bearish" and sequence.get("buy_side_liquidity_taken"):
            return True
        if direction == "bullish" and sequence.get("sell_side_liquidity_taken"):
            return True
    return False


def _displacement_summary(direction: str, move: Mapping[str, Any]) -> dict[str, Any]:
    state = str(move.get("state") or "")
    evidence = _mapping(move.get("evidence"))
    break_count = evidence.get("same_direction_15m_break_count")
    try:
        broken = int(break_count or 0) > 0
    except (TypeError, ValueError):
        broken = state in {"EARLY_CONTINUATION_CONFIRMATION", "CONTINUATION_CONFIRMED", "MOVE_STARTED_NOT_CHASEABLE"}
    quality = "strong" if state == "CONTINUATION_CONFIRMED" else "forming" if broken else "not_confirmed"
    return {
        "direction": direction if direction in {"bullish", "bearish"} else None,
        "quality": quality,
        "structure_broken": broken,
        "move_state": state or "unknown",
        "same_direction_15m_break_count": break_count,
    }


def _liquidity_taken(liquidity_sequence: Mapping[str, Any], direction: str) -> list[str]:
    taken: list[str] = []
    for tf in ("15m", "1h", "4h", "1d"):
        sequence = _mapping(liquidity_sequence.get(tf))
        if sequence.get("buy_side_liquidity_taken"):
            taken.append(f"{tf} buy-side liquidity swept")
        if sequence.get("sell_side_liquidity_taken"):
            taken.append(f"{tf} sell-side liquidity swept")
    if taken:
        return taken[:4]
    if direction == "bearish":
        return ["No certified buy-side sweep promoted yet."]
    if direction == "bullish":
        return ["No certified sell-side sweep promoted yet."]
    return ["No certified liquidity sweep promoted yet."]


def _confirmation_steps(confirmation: Mapping[str, Any], continuation: list[str], entry_style: Mapping[str, Any]) -> list[str]:
    steps: list[str] = []
    summary = confirmation.get("summary")
    if summary:
        steps.append(str(summary))
    steps.extend(str(item) for item in continuation[:3])
    if entry_style.get("state"):
        steps.append(f"entry style: {entry_style.get('state')}")
    return _unique_strings(steps)


def _entry_status(official_state: str, entry_style: Mapping[str, Any]) -> str:
    if official_state == TRADE_PLAN_READY:
        return "entry_ready"
    if official_state == "MOVE_STARTED_NOT_CHASEABLE":
        return "missed_trade_no_chase"
    if official_state in {"WAIT_FOR_RETRACE_TO_SUPPLY", "WAIT_FOR_RETRACE_TO_DEMAND"}:
        return "not_ready_until_retrace_and_rejection"
    if official_state == "POI_TOUCHED_AWAIT_CONFIRMATION":
        return "not_ready_until_15m_confirmation"
    if entry_style.get("state") == "CONSERVATIVE_CONFIRMATION_REQUIRED":
        return "conservative_confirmation_required"
    return "watch_only"


def _unique_draws(draws: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for draw in draws:
        key = (str(draw.get("timeframe")), str(draw.get("price")), str(draw.get("label")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(draw)
    return unique


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
