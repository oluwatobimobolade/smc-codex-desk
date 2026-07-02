"""Colleague brain v2: cognitive correctness pipeline.

This is an observe-only orchestration layer. Its job is to decide whether the
system is allowed to reason, not to generate trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from smc_desk.colleague.decision_memory_graph import (
    append_decision_memory,
    build_decision_memory_record,
    supersede_prior_decisions,
    write_active_truth_index,
)
from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from smc_desk.data.schemas import Candle
from smc_desk.data.truth_validator import MarketTruthReport, validate_market_truth
from smc_desk.decision.contradiction_resolver import (
    ContradictionResolution,
    resolve_timeframe_contradictions,
)
from smc_desk.decision.execution_readiness import evaluate_execution_readiness
from smc_desk.decision.inducement_continuation_classifier import classify_inducement_continuation
from smc_desk.decision.refusal_engine import RefusalDecision, evaluate_refusal
from smc_desk.decision.timeframe_role_engine import assess_timeframe_roles
from smc_desk.decision.uncertainty_engine import UncertaintyAssessment, score_uncertainty
from smc_desk.decision.watch_state_engine import evaluate_watch_state
from smc_desk.perception.engine_v2 import PerceptionEngineV2
from smc_desk.perception.liquidity_sequence import build_liquidity_sequence_by_timeframe
from smc_desk.perception.poi_lifecycle import build_poi_lifecycle_by_timeframe
from smc_desk.perception.regime_engine import RegimeAssessment, classify_market_regime
from smc_desk.perception.structure_hierarchy import build_mtf_structure_hierarchy, hierarchy_timeframe_signals
from smc_desk.rules import RuleConfig, load_rule_config


@dataclass(frozen=True)
class ColleagueBrainV2Result:
    symbol: str
    decision_time: datetime
    truth_report: MarketTruthReport
    regime: RegimeAssessment | None
    perception_by_tf: dict[str, dict[str, Any]]
    structure_hierarchy: dict[str, dict[str, Any]]
    poi_lifecycle: dict[str, list[dict[str, Any]]]
    liquidity_sequence: dict[str, dict[str, Any]] | None
    timeframe_roles: dict[str, Any] | None
    watch_state: dict[str, Any] | None
    inducement_continuation: dict[str, Any] | None
    execution_readiness: dict[str, Any] | None
    contradiction: ContradictionResolution | None
    uncertainty: UncertaintyAssessment | None
    refusal: RefusalDecision
    memory_record: dict[str, Any] | None = None

    def _final_state(self) -> str:
        """Communicated headline: the watch narrative when present, else the authority verdict.

        Execution authority still comes solely from ``final_action``. Any WATCH_*/POI_*/AWAIT_*
        state is observe-only; ``signal_allowed`` is False everywhere.
        """
        if self.watch_state:
            state = str(self.watch_state.get("final_state") or "").strip()
            if state:
                return state
        return self.refusal.final_action

    def to_dict(self) -> dict:
        payload = {
            "pipeline": "colleague_brain_v2",
            "authority": {
                "market_truth": "hard_gate",
                "perception": "research_authority_after_truth_pass",
                "decision": "observe_only_no_execution",
                "paper_execution": "disabled",
                "live_execution": "disabled",
                "capital_risk": 0,
            },
            "symbol": self.symbol,
            "decision_time": self.decision_time.isoformat(),
            "truth_report": self.truth_report.to_dict(),
            "regime": None if self.regime is None else self.regime.to_dict(),
            "perception_status": "refused_not_run" if self.truth_report.refuse_perception else "completed",
            "perception_by_tf": self.perception_by_tf,
            "structure_hierarchy": self.structure_hierarchy,
            "poi_lifecycle": self.poi_lifecycle,
            "liquidity_sequence": self.liquidity_sequence,
            "timeframe_roles": self.timeframe_roles,
            "watch_state": self.watch_state,
            "inducement_continuation": self.inducement_continuation,
            "execution_readiness": self.execution_readiness,
            "contradiction": None if self.contradiction is None else self.contradiction.to_dict(),
            "uncertainty": None if self.uncertainty is None else self.uncertainty.to_dict(),
            "refusal": self.refusal.to_dict(),
            "final_action": self.refusal.final_action,
            "final_state": self._final_state(),
            "signal_allowed": bool(self.refusal.signal_allowed),
            "memory_record": self.memory_record,
        }
        payload["smc_narrative_authority"] = build_smc_narrative_authority(
            symbol=self.symbol,
            cognitive_result=payload,
        )
        return payload


def run_colleague_brain_v2(
    *,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    decision_time: datetime,
    symbol: str,
    expected_timeframes: Sequence[str] = ("15m", "1h", "4h", "1d"),
    provider_feeds: Mapping[str, Mapping[str, Sequence[Candle]]] | None = None,
    memory_path: str | None = None,
    config: RuleConfig | None = None,
) -> ColleagueBrainV2Result:
    """Run the cognitive correctness pipeline."""
    config = config or load_rule_config()
    truth_report = validate_market_truth(
        candles_by_timeframe,
        decision_time,
        expected_instrument=symbol,
        expected_timeframes=expected_timeframes,
        provider_feeds=provider_feeds,
    )
    if truth_report.refuse_perception:
        refusal = evaluate_refusal(truth_report=truth_report)
        memory_record = _build_and_maybe_write_memory(
            symbol=symbol,
            decision_time=decision_time,
            candles_by_timeframe=candles_by_timeframe,
            regime=None,
            fvg_state=None,
            contradiction=None,
            refusal=refusal,
            memory_path=memory_path,
            current_state=refusal.final_action,
        )
        return ColleagueBrainV2Result(
            symbol=symbol,
            decision_time=decision_time,
            truth_report=truth_report,
            regime=None,
            perception_by_tf={},
            structure_hierarchy={},
            poi_lifecycle={},
            liquidity_sequence=None,
            timeframe_roles=None,
            watch_state=None,
            inducement_continuation=None,
            execution_readiness=None,
            contradiction=None,
            uncertainty=None,
            refusal=refusal,
            memory_record=memory_record,
        )

    regime_source = candles_by_timeframe.get("15m") or next(iter(candles_by_timeframe.values()))
    regime = classify_market_regime(regime_source)
    perception_by_tf = _run_perception(
        candles_by_timeframe=candles_by_timeframe,
        decision_time=decision_time,
        symbol=symbol,
        expected_timeframes=expected_timeframes,
        config=config,
    )
    current_prices = _current_prices(candles_by_timeframe)
    structure_hierarchy = build_mtf_structure_hierarchy(perception_by_tf, current_prices=current_prices)
    poi_lifecycle = build_poi_lifecycle_by_timeframe(
        perception_by_tf,
        structure_hierarchy,
        current_prices=current_prices,
    )
    liquidity_sequence = build_liquidity_sequence_by_timeframe(perception_by_tf)
    timeframe_roles = assess_timeframe_roles(structure_hierarchy).to_dict()
    watch_state = evaluate_watch_state(
        hierarchy_by_tf=structure_hierarchy,
        roles=timeframe_roles,
        pois_by_tf=poi_lifecycle,
    ).to_dict()
    inducement_continuation = classify_inducement_continuation(
        perception_by_tf=perception_by_tf,
        liquidity_sequence_by_tf=liquidity_sequence,
        watch_state=watch_state,
        structure_hierarchy=structure_hierarchy,
    ).to_dict()
    execution_readiness = evaluate_execution_readiness(
        watch_state=watch_state,
        inducement_continuation=inducement_continuation,
    ).to_dict()
    signals = hierarchy_timeframe_signals(structure_hierarchy)
    contradiction = resolve_timeframe_contradictions(signals)
    uncertainty = score_uncertainty(
        truth_report=truth_report,
        regime_assessment=regime,
        contradiction_resolution=contradiction,
        perception_by_tf=perception_by_tf,
    )
    refusal = evaluate_refusal(
        truth_report=truth_report,
        regime_assessment=regime,
        contradiction_resolution=contradiction,
        uncertainty_assessment=uncertainty,
    )
    refusal = _apply_watch_state_gate(refusal, watch_state)
    current_state = watch_state.get("final_state") if watch_state else refusal.final_action
    memory_record = _build_and_maybe_write_memory(
        symbol=symbol,
        decision_time=decision_time,
        candles_by_timeframe=candles_by_timeframe,
        regime=regime.to_dict(),
        fvg_state=_summarize_fvgs(perception_by_tf),
        contradiction=contradiction.to_dict(),
        refusal=refusal,
        memory_path=memory_path,
        current_state=current_state,
    )
    return ColleagueBrainV2Result(
        symbol=symbol,
        decision_time=decision_time,
        truth_report=truth_report,
        regime=regime,
        perception_by_tf=perception_by_tf,
        structure_hierarchy=structure_hierarchy,
        poi_lifecycle=poi_lifecycle,
        liquidity_sequence=liquidity_sequence,
        timeframe_roles=timeframe_roles,
        watch_state=watch_state,
        inducement_continuation=inducement_continuation,
        execution_readiness=execution_readiness,
        contradiction=contradiction,
        uncertainty=uncertainty,
        refusal=refusal,
        memory_record=memory_record,
    )


def _run_perception(
    *,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    decision_time: datetime,
    symbol: str,
    expected_timeframes: Sequence[str],
    config: RuleConfig,
) -> dict[str, dict[str, Any]]:
    perception_by_tf: dict[str, dict[str, Any]] = {}
    for timeframe in expected_timeframes:
        candles = list(candles_by_timeframe[timeframe])
        engine = PerceptionEngineV2(
            expected_instrument=symbol,
            expected_timeframe=timeframe,
            config=config,
        )
        snapshot = engine.analyze(candles, decision_time)
        payload = snapshot.model_dump(mode="json")
        payload["candle_count"] = len(candles)
        if candles:
            payload["last_close"] = candles[-1].close_time.isoformat()
            payload["last_price"] = str(candles[-1].close)
        perception_by_tf[timeframe] = payload
    return perception_by_tf


def _summarize_fvgs(perception_by_tf: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    by_tf: dict[str, Any] = {}
    total = 0
    active = 0
    for timeframe, snapshot in perception_by_tf.items():
        fvgs = snapshot.get("fvgs", []) or []
        total += len(fvgs)
        active_count = 0
        for fvg in fvgs:
            mitigation = str(fvg.get("mitigation_status", "")).lower()
            terminal = str(fvg.get("terminal_reason", "")).lower()
            if mitigation != "full" and terminal in {"", "none"}:
                active_count += 1
        active += active_count
        by_tf[timeframe] = {"total": len(fvgs), "active_or_unmitigated": active_count}
    return {"status": "summarized", "total": total, "active_or_unmitigated": active, "by_timeframe": by_tf}


def _build_and_maybe_write_memory(
    *,
    symbol: str,
    decision_time: datetime,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    regime: dict[str, Any] | None,
    fvg_state: dict[str, Any] | None,
    contradiction: dict[str, Any] | None,
    refusal: RefusalDecision,
    memory_path: str | None,
    current_state: str | None = None,
) -> dict[str, Any] | None:
    if memory_path is None:
        return None
    final_decision = refusal.to_dict()
    if current_state:
        final_decision = {**final_decision, "final_state": current_state}
    record = build_decision_memory_record(
        symbol=symbol,
        decision_time=decision_time,
        market_state_snapshot=_market_state_snapshot(candles_by_timeframe),
        regime=regime,
        fvg_state=fvg_state,
        contradiction_result=contradiction,
        final_decision=final_decision,
    )
    append_decision_memory(memory_path, record)
    if current_state:
        superseded_ids = supersede_prior_decisions(
            memory_path,
            symbol=symbol,
            current_decision_id=record["decision_id"],
            current_state=current_state,
            reason="new cognitive state contradicts prior interpretation",
        )
        write_active_truth_index(
            memory_path,
            symbol=symbol,
            current_decision_id=record["decision_id"],
            current_state=current_state,
            superseded_ids=superseded_ids,
            reason="latest V6 cognitive state is the active interpretation",
        )
    return record


def _market_state_snapshot(candles_by_timeframe: Mapping[str, Sequence[Candle]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for timeframe, candles_raw in candles_by_timeframe.items():
        candles = list(candles_raw)
        if not candles:
            summary[timeframe] = {"candle_count": 0}
            continue
        summary[timeframe] = {
            "candle_count": len(candles),
            "first_open": candles[0].open_time.isoformat(),
            "last_open": candles[-1].open_time.isoformat(),
            "last_close": candles[-1].close_time.isoformat(),
            "last_price": str(candles[-1].close),
        }
    return summary


def _current_prices(candles_by_timeframe: Mapping[str, Sequence[Candle]]) -> dict[str, Any]:
    prices: dict[str, Any] = {}
    for timeframe, candles_raw in candles_by_timeframe.items():
        candles = list(candles_raw)
        if candles:
            prices[timeframe] = candles[-1].close
    return prices


def _apply_watch_state_gate(refusal: RefusalDecision, watch_state: Mapping[str, Any] | None) -> RefusalDecision:
    if not watch_state:
        return refusal
    if watch_state.get("signal_allowed"):
        return refusal
    state = str(watch_state.get("final_state", ""))
    if not state or state == "EXECUTE":
        return refusal
    reasons = list(refusal.reasons)
    reason = f"SMC watch state is {state}; execution confirmation is incomplete."
    if reason not in reasons:
        reasons.append(reason)
    blocking_codes = list(refusal.blocking_codes)
    if "watch_state_not_executable" not in blocking_codes:
        blocking_codes.append("watch_state_not_executable")
    return RefusalDecision(
        final_action="NO_SIGNAL",
        perception_allowed=refusal.perception_allowed,
        signal_allowed=False,
        reasons=reasons,
        blocking_codes=blocking_codes,
    )
