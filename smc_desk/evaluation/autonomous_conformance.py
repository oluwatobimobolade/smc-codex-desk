"""Orchestrate autonomous definition conformance and adversarial checks.

The production detector and clean-room oracle meet only in this module.  A
matching result certifies the frozen house definition for the evaluated label
families; it does not certify a mechanism, forecast, strategy, or trade.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

import pandas as pd

from smc_desk.data.hashing import object_sha256
from smc_desk.evaluation.autonomous_truth import (
    compare_claim_sets,
    evaluate_robustness_envelope,
    issue_definition_conformance_certificate,
    load_autonomous_truth_constitution,
    normalized_claim_signature,
)
from smc_desk.evaluation.production_claim_adapter import run_production_claim_adapter
from smc_desk.evaluation.reference_oracle import (
    OracleConfig,
    TIMEFRAME_DURATIONS,
    run_reference_oracle,
    run_reference_robustness_profiles,
)


CERTIFIED_LABEL_FAMILIES = ("swing", "fair_value_gap")
DIAGNOSTIC_LABEL_FAMILIES = ("structural_level_interaction",)


def run_autonomous_definition_conformance(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    session_profile: str = "continuous",
) -> dict[str, Any]:
    """Run independent implementations and issue a fail-closed certificate."""
    constitution = load_autonomous_truth_constitution()
    canonical_config = OracleConfig.from_mapping(constitution.profiles["canonical"])
    reference = run_reference_oracle(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=canonical_config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    production = run_production_claim_adapter(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        session_profile=session_profile,
    )
    comparisons = [
        compare_claim_sets(
            label_family=family,
            reference_claims=reference["claims"][family],
            production_claims=production["claims"][family],
        )
        for family in CERTIFIED_LABEL_FAMILIES
    ]

    profiles = run_reference_robustness_profiles(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        profiles=constitution.profiles,
        session_profile=session_profile,
    )
    robustness = evaluate_robustness_envelope(
        {
            name: [
                claim
                for family in CERTIFIED_LABEL_FAMILIES
                for claim in result["claims"][family]
            ]
            for name, result in profiles.items()
        }
    )
    metamorphic = run_reference_metamorphic_checks(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=canonical_config,
        session_profile=session_profile,
    )
    certificate = issue_definition_conformance_certificate(
        market=market,
        timeframe=timeframe,
        decision_time=_iso(decision_time),
        data_sha256=reference["data_sha256"],
        reference_oracle={
            "schema": reference["schema"],
            "version": reference["oracle_version"],
            "output_sha256": reference["oracle_output_sha256"],
        },
        comparisons=comparisons,
        robustness=robustness,
        evaluated_label_families=CERTIFIED_LABEL_FAMILIES,
        unevaluated_label_families=(
            *DIAGNOSTIC_LABEL_FAMILIES,
            "order_block",
            "liquidity_draw",
            "choch_mss_bos_semantics",
        ),
        metamorphic_results=metamorphic,
    )
    return {
        "schema": "autonomous_definition_conformance_run_v1",
        "certificate": certificate,
        "reference": reference,
        "production": production,
        "diagnostics": {
            "structural_level_interaction": {
                "status": "NOT_EVALUATED",
                "reason": "independent_target_ownership_and_protected_point_state_machine_not_yet_available",
                "production_claim_count": len(production["claims"]["structural_level_interaction"]),
            },
            "diagnostic_results_never_promote_certificate": True,
        },
        "robustness_profiles": profiles,
    }


def run_autonomous_conformance_bundle(
    timeframe_dfs: Mapping[str, pd.DataFrame],
    *,
    market: str,
    session_profile: str | None = None,
    minimum_depths: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Run the gate per timeframe and keep failures as explicit data states."""
    by_timeframe: dict[str, Any] = {}
    full_runs: dict[str, Any] = {}
    input_preparation: dict[str, Any] = {}
    if session_profile is None:
        normalized_market = market.upper().replace("/", "").replace("-", "")
        session_profile = (
            "continuous"
            if any(token in normalized_market for token in ("USDT", "BTC", "ETH"))
            else "forex_5d"
        )
    if session_profile not in {"continuous", "forex_5d"}:
        raise ValueError(f"Unsupported session_profile: {session_profile}")
    for timeframe, frame in sorted(timeframe_dfs.items()):
        duration = TIMEFRAME_DURATIONS.get(timeframe)
        if duration is None:
            by_timeframe[timeframe] = _data_failed_certificate(
                market=market, timeframe=timeframe, reason="unsupported_timeframe"
            )
            continue
        try:
            work = frame.copy()
            if "timestamp" not in work.columns:
                work = work.reset_index().rename(columns={work.index.name or "index": "timestamp"})
            work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
            work = work.sort_values("timestamp").reset_index(drop=True)
            preparation = {
                "status": "UNCHANGED",
                "original_rows": len(work),
                "evaluated_rows": len(work),
                "session_profile": session_profile,
            }
            if session_profile == "forex_5d" and minimum_depths is not None:
                latest, segment_report = _latest_contiguous_segment(
                    work,
                    timeframe=timeframe,
                    session_profile=session_profile,
                )
                required = int(minimum_depths.get(timeframe, 0) or 0)
                if segment_report["historical_gap_detected"] and len(latest) >= required:
                    work = latest
                    preparation = {
                        **segment_report,
                        "status": "LATEST_CONTIGUOUS_SEGMENT",
                        "minimum_required": required,
                        "evaluated_rows": len(work),
                    }
                elif segment_report["historical_gap_detected"]:
                    preparation = {
                        **segment_report,
                        "status": "TRIM_REFUSED_INSUFFICIENT_DEPTH",
                        "minimum_required": required,
                        "evaluated_rows": len(work),
                    }
            input_preparation[timeframe] = preparation
            timestamps = pd.to_datetime(work["timestamp"], utc=True)
            decision_time = timestamps.iloc[-1] + duration
            result = run_autonomous_definition_conformance(
                work,
                market=market,
                timeframe=timeframe,
                decision_time=decision_time,
                session_profile=session_profile,
            )
            full_runs[timeframe] = result
            by_timeframe[timeframe] = {
                "certificate": result["certificate"],
                "diagnostics": result["diagnostics"],
            }
        except Exception as exc:  # fail closed, but do not erase the rest of the evidence pack
            input_preparation.setdefault(
                timeframe,
                {
                    "status": "PREPARATION_FAILED",
                    "original_rows": len(frame),
                    "evaluated_rows": 0,
                    "session_profile": session_profile,
                },
            )
            by_timeframe[timeframe] = _data_failed_certificate(
                market=market,
                timeframe=timeframe,
                reason=f"{type(exc).__name__}:{str(exc)[:240]}",
            )
    statuses = [
        str((item.get("certificate") or {}).get("status") or "DATA_FAILED")
        for item in by_timeframe.values()
    ]
    if any(status in {"IMPLEMENTATION_CONFLICT", "DATA_FAILED", "DOCTRINE_UNDEFINED"} for status in statuses):
        status = "BLOCKED"
    elif any(status == "BOUNDARY_SENSITIVE" for status in statuses):
        status = "BOUNDARY_SENSITIVE"
    elif statuses and all(status == "DEFINITION_CONFORMANT" for status in statuses):
        status = "DEFINITION_CONFORMANT"
    else:
        status = "NOT_EVALUATED"
    bundle = {
        "schema": "autonomous_definition_conformance_bundle_v1",
        "status": status,
        "market": market,
        "session_profile": session_profile,
        "input_preparation": input_preparation,
        "by_timeframe": by_timeframe,
        "authority_contract": {
            "human_adjudication_used": False,
            "definition_conformance_only": True,
            "structure_semantics_certified": False,
            "order_blocks_certified": False,
            "liquidity_draws_certified": False,
            "signal_allowed": False,
            "paper_execution_allowed": False,
            "live_execution_allowed": False,
        },
    }
    bundle["bundle_sha256"] = object_sha256(bundle)
    return {"bundle": bundle, "full_runs": full_runs}


def _latest_contiguous_segment(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    session_profile: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return only observations after the latest unexplained historical gap.

    This is a scope reduction, not a data repair.  Scheduled FX weekend
    closures remain in the certified sample.  A genuine missing interval can
    be excluded only when the caller's minimum context depth still survives;
    the bundle records the exact cut so old corruption cannot silently poison
    every future run or silently disappear from provenance.
    """
    if len(frame) <= 1:
        return frame, {
            "historical_gap_detected": False,
            "original_rows": len(frame),
            "candidate_rows": len(frame),
            "session_profile": session_profile,
        }
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    duration = TIMEFRAME_DURATIONS[timeframe]
    latest_gap_index: int | None = None
    latest_gap_previous_close: pd.Timestamp | None = None
    latest_gap_next_open: pd.Timestamp | None = None
    for index in range(1, len(timestamps)):
        previous_close = pd.Timestamp(timestamps.iloc[index - 1]) + duration
        next_open = pd.Timestamp(timestamps.iloc[index])
        if next_open == previous_close:
            continue
        if _expected_conformance_session_closure(
            previous_close,
            next_open,
            session_profile=session_profile,
            timeframe=timeframe,
        ):
            continue
        latest_gap_index = index
        latest_gap_previous_close = previous_close
        latest_gap_next_open = next_open
    if latest_gap_index is None:
        return frame, {
            "historical_gap_detected": False,
            "original_rows": len(frame),
            "candidate_rows": len(frame),
            "session_profile": session_profile,
        }
    latest = frame.iloc[latest_gap_index:].reset_index(drop=True)
    return latest, {
        "historical_gap_detected": True,
        "original_rows": len(frame),
        "candidate_rows": len(latest),
        "session_profile": session_profile,
        "latest_gap_previous_close": _iso(latest_gap_previous_close),
        "latest_gap_next_open": _iso(latest_gap_next_open),
        "expected_step": str(duration),
    }


def _expected_conformance_session_closure(
    previous_close: pd.Timestamp,
    next_open: pd.Timestamp,
    *,
    session_profile: str,
    timeframe: str,
) -> bool:
    if session_profile != "forex_5d":
        return False
    hours = (next_open - previous_close).total_seconds() / 3600.0
    if timeframe == "1d":
        return -1.5 <= hours <= 120.0
    return (
        24.0 <= hours <= 75.0
        and previous_close.weekday() in {4, 5}
        and next_open.weekday() in {6, 0}
    )


def _data_failed_certificate(*, market: str, timeframe: str, reason: str) -> dict[str, Any]:
    return {
        "certificate": {
            "schema": "autonomous_definition_conformance_certificate_v1",
            "status": "DATA_FAILED",
            "scope": {"market": market, "timeframe": timeframe, "evidence_layer": "definition_conformance"},
            "failures": [reason],
            "authority_contract": {"signal_allowed": False, "live_execution_allowed": False},
        },
        "diagnostics": {},
    }


def run_reference_metamorphic_checks(
    frame: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    decision_time: str | pd.Timestamp,
    config: OracleConfig | None = None,
    session_profile: str = "continuous",
) -> list[dict[str, Any]]:
    """Exercise relations that should hold without any human labels."""
    config = config or OracleConfig()
    baseline = run_reference_oracle(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks: list[dict[str, Any]] = []

    replay = run_reference_oracle(
        frame,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks.append(_check("deterministic_replay", replay == baseline))

    future = _append_future_candle(frame, timeframe=timeframe, decision_time=decision_time)
    future_result = run_reference_oracle(
        future,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks.append(_check("append_future_candles_after_decision", future_result == baseline))

    scaled = _transform_prices(frame, lambda value: value * Decimal("7"))
    scaled_inverse = _exact_transformed_price_inverse(frame, scaled)
    scaled_result = run_reference_oracle(
        scaled,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks.append(
        _check(
            "positive_price_scale",
            _transformed_claim_sets(scaled_result, inverse=scaled_inverse)
            == _claim_sets(baseline),
        )
    )

    extrema = [Decimal(str(value)) for column in ("low", "high") for value in frame[column].tolist()]
    shift = max(extrema).copy_abs() + Decimal("37")
    translated = _transform_prices(frame, lambda value: value + shift)
    translated_inverse = _exact_transformed_price_inverse(frame, translated)
    translated_result = run_reference_oracle(
        translated,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks.append(
        _check(
            "price_translation",
            _transformed_claim_sets(
                translated_result,
                inverse=translated_inverse,
                raw_fvg=True,
            )
            == _claim_sets(baseline, raw_fvg=True),
        )
    )

    anchor = max(extrema) + min(extrema)
    mirrored = _mirror_prices(frame, anchor=anchor)
    mirrored_inverse = _exact_transformed_price_inverse(
        frame,
        mirrored,
        mirrored_extrema=True,
    )
    mirrored_result = run_reference_oracle(
        mirrored,
        market=market,
        timeframe=timeframe,
        decision_time=decision_time,
        config=config,
        session_profile=session_profile,
        include_diagnostics=False,
    )
    checks.append(
        _check(
            "vertical_mirror",
            _transformed_claim_sets(
                mirrored_result,
                inverse=mirrored_inverse,
                raw_fvg=True,
                mirror_direction=True,
                swap_price_bounds=True,
            )
            == _claim_sets(baseline, raw_fvg=True),
        )
    )

    closed = _closed_rows(frame, timeframe=timeframe, decision_time=decision_time)
    if len(closed) > 1:
        rollback_frame = closed.iloc[:-1].copy()
        # The removed candle opens exactly when the preceding candle closes.
        # Re-run at that boundary; using the removed candle's close would allow
        # the baseline projection to retain evidence created by that candle.
        rollback_decision = pd.Timestamp(closed.iloc[-1]["timestamp"])
        rollback = run_reference_oracle(
            rollback_frame,
            market=market,
            timeframe=timeframe,
            decision_time=rollback_decision,
            config=config,
            session_profile=session_profile,
            include_diagnostics=False,
        )
        projected = _claims_confirmed_by(baseline, rollback_decision)
        checks.append(_check("one_candle_rollback", _claim_sets(rollback) == projected))
    else:
        checks.append(_check("one_candle_rollback", False, detail="fewer_than_two_closed_candles"))
    return checks


def _claim_sets(result: Mapping[str, Any], *, raw_fvg: bool = False) -> dict[str, set[tuple[Any, ...]]]:
    output: dict[str, set[tuple[Any, ...]]] = {}
    for family in CERTIFIED_LABEL_FAMILIES:
        output[family] = {
            _comparison_signature(claim, raw_fvg=raw_fvg)
            for claim in result["claims"][family]
        }
    return output


def _transformed_claim_sets(
    result: Mapping[str, Any],
    *,
    inverse,
    raw_fvg: bool = False,
    mirror_direction: bool = False,
    swap_price_bounds: bool = False,
) -> dict[str, set[tuple[Any, ...]]]:
    transformed: dict[str, list[dict[str, Any]]] = {}
    for family in CERTIFIED_LABEL_FAMILIES:
        transformed[family] = []
        for source in result["claims"][family]:
            claim = dict(source)
            low = inverse(Decimal(str(source["price_low"])))
            high = inverse(Decimal(str(source["price_high"])))
            if swap_price_bounds:
                low, high = high, low
            claim["price_low"] = _number(low)
            claim["price_high"] = _number(high)
            if mirror_direction:
                claim["direction"] = _opposite(str(claim["direction"]))
            transformed[family].append(claim)
    return _claim_sets({"claims": transformed}, raw_fvg=raw_fvg)


def _comparison_signature(claim: Mapping[str, Any], *, raw_fvg: bool) -> tuple[Any, ...]:
    signature = list(normalized_claim_signature(claim))
    if raw_fvg and claim.get("label_family") == "fair_value_gap":
        signature[-1] = "RAW_GEOMETRY"
    return tuple(signature)


def _claims_confirmed_by(result: Mapping[str, Any], cutoff: pd.Timestamp) -> dict[str, set[tuple[Any, ...]]]:
    normalized_cutoff = _timestamp(cutoff)
    projected: dict[str, set[tuple[Any, ...]]] = {}
    for family in CERTIFIED_LABEL_FAMILIES:
        projected[family] = {
            _comparison_signature(claim, raw_fvg=False)
            for claim in result["claims"][family]
            if claim.get("confirmed_at") and _timestamp(claim["confirmed_at"]) <= normalized_cutoff
        }
    return projected


def _append_future_candle(
    frame: pd.DataFrame,
    *,
    timeframe: str,
    decision_time: str | pd.Timestamp,
) -> pd.DataFrame:
    work = frame.copy()
    duration = TIMEFRAME_DURATIONS[timeframe]
    cutoff = _timestamp(decision_time)
    last = work.iloc[-1].copy()
    last["timestamp"] = max(_timestamp(last["timestamp"]) + duration, cutoff + duration)
    return pd.concat([work, pd.DataFrame([last])], ignore_index=True)


def _closed_rows(frame: pd.DataFrame, *, timeframe: str, decision_time: str | pd.Timestamp) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    cutoff = _timestamp(decision_time)
    return work.loc[work["timestamp"] + TIMEFRAME_DURATIONS[timeframe] <= cutoff].reset_index(drop=True)


def _transform_prices(frame: pd.DataFrame, transform) -> pd.DataFrame:
    work = frame.copy()
    for column in ("open", "high", "low", "close"):
        work[column] = [float(transform(Decimal(str(value)))) for value in work[column]]
    return work


def _mirror_prices(frame: pd.DataFrame, *, anchor: Decimal) -> pd.DataFrame:
    work = frame.copy()
    original = frame[["open", "high", "low", "close"]].copy()
    work["open"] = [float(anchor - Decimal(str(value))) for value in original["open"]]
    work["close"] = [float(anchor - Decimal(str(value))) for value in original["close"]]
    work["high"] = [float(anchor - Decimal(str(value))) for value in original["low"]]
    work["low"] = [float(anchor - Decimal(str(value))) for value in original["high"]]
    return work


def _exact_transformed_price_inverse(
    source: pd.DataFrame,
    transformed: pd.DataFrame,
    *,
    mirrored_extrema: bool = False,
):
    """Map transformed float values back to their exact source observations.

    Metamorphic transforms intentionally pass through pandas/numpy float
    storage.  Algebraically inverting the serialized float (for example,
    ``Decimal(str(value)) / 7``) manufactures a different decimal tail from
    the source observation and makes an unchanged claim set look different.
    The transform is bijective for the finite OHLC observations used here, so
    bind each stored transformed value directly to the exact stored source
    value.  A collision between different source prices is refused rather
    than silently weakening the check.
    """
    inverse: dict[Decimal, Decimal] = {}
    column_pairs = (
        (("open", "open"), ("low", "high"), ("high", "low"), ("close", "close"))
        if mirrored_extrema
        else (("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"))
    )
    for source_column, transformed_column in column_pairs:
        for original, changed in zip(
            source[source_column],
            transformed[transformed_column],
            strict=True,
        ):
            changed_key = Decimal(str(changed))
            original_value = Decimal(str(original))
            prior = inverse.get(changed_key)
            if prior is not None and prior != original_value:
                raise ValueError("Metamorphic price transform is not bijective at stored precision.")
            inverse[changed_key] = original_value

    def restore(value: Decimal) -> Decimal:
        try:
            return inverse[value]
        except KeyError as exc:
            raise ValueError("Metamorphic claim price is not bound to a transformed source observation.") from exc

    return restore


def _check(relation: str, passed: bool, *, detail: str = "") -> dict[str, Any]:
    return {"relation": relation, "passed": bool(passed), "detail": detail}


def _opposite(direction: str) -> str:
    return {"bullish": "bearish", "bearish": "bullish"}.get(direction, direction)


def _number(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _iso(value: Any) -> str:
    return _timestamp(value).isoformat().replace("+00:00", "Z")


__all__ = [
    "CERTIFIED_LABEL_FAMILIES",
    "DIAGNOSTIC_LABEL_FAMILIES",
    "run_autonomous_definition_conformance",
    "run_autonomous_conformance_bundle",
    "run_reference_metamorphic_checks",
]
