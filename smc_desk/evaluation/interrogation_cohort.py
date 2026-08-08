"""Build sealed, point-in-time SMC perception interrogation cohorts.

Selection is deliberately engine-blind: cases are stratified by rolling
volatility and time, never by later reaction, detector output, or profitability.
The generated cohort is a review instrument, not gold truth.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from PIL import Image, ImageFilter

from smc_desk.evaluation.perception_gauntlet import (
    PROBES as GAUNTLET_PROBES,
    gauntlet_protocol_manifest,
    response_template as gauntlet_response_template,
)
from smc_desk.evaluation.semantic_metamorphic import (
    build_semantic_metamorphic_frames,
    verify_transformation,
)


DIMENSION_WEIGHTS = {
    "raw_candle_and_level_perception": 10,
    "exact_geometric_grounding": 15,
    "swing_hierarchy": 15,
    "structural_classification": 10,
    "protected_point_and_causal_reasoning": 15,
    "liquidity_and_sweep_classification": 10,
    "range_poi_and_inducement_reasoning": 10,
    "temporal_validity_and_no_lookahead": 10,
    "uncertainty_and_abstention": 3,
    "annotation_communication": 2,
}

CATASTROPHIC_GATES = (
    "future_candle_used",
    "invented_level_or_candle",
    "internal_labeled_external_without_justification",
    "ltf_choch_reversed_htf_structure",
    "wick_called_confirmed_close_bos",
    "annotation_changed_coordinates",
    "poi_ranked_with_future_reaction",
    "every_penetration_called_sweep",
    "fabricated_confidence",
    "failed_to_abstain_without_evidence",
)

HARD_QUESTIONS = (
    "What is the active external structure, and which exact event established it?",
    "What is the active internal structure, and why does it not override external structure?",
    "Which swing is protected, and when did protected status begin?",
    "What was the earliest candle at which the latest BOS could be declared?",
    "Was the last liquidity penetration a sweep, failed breakout, or accepted breakout at this cutoff?",
    "What evidence remains missing before that classification can be final?",
    "Identify the causal origin of displacement, not merely the last opposite-coloured candle.",
    "Which visible FVG is technically valid but structurally irrelevant?",
    "Rank the top three POIs without using later reactions.",
    "What is the active dealing range, and what event activated it?",
    "Give a competing valid range interpretation and evidence that resolves it.",
    "Which alleged inducement is most likely retrospective?",
    "What changed after the lower-timeframe CHoCH, and what did not change?",
    "What minimum one-candle modification would change structural classification?",
    "Which conclusions survive recolouring, resizing, cropping, and anonymisation?",
    "What cannot be determined from the supplied chart?",
    "Which exact claim has the lowest justified confidence, and why?",
    "With future candles hidden, which annotations must be removed or downgraded?",
    "Construct the shortest evidence-grounded causal chain for the current state.",
    "Should the system abstain from a trade plan, and which exact conditions are missing?",
)

TIMEFRAME_RULES = {
    "15m": ("15min", pd.Timedelta(minutes=15), 160),
    "1h": ("1h", pd.Timedelta(hours=1), 160),
    "4h": ("4h", pd.Timedelta(hours=4), 120),
    "1d": ("1D", pd.Timedelta(days=1), 90),
}

VOLATILITY_TARGETS = (0.05, 0.20, 0.40, 0.60, 0.80, 0.95)


def load_canonical_15m(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"OHLCV missing required columns: {missing}")
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("OHLCV contains NaN prices")
    return frame


def select_blind_cutoffs(
    frame: pd.DataFrame,
    *,
    count: int = 6,
    minimum_history_bars: int = 12_000,
    minimum_spacing_days: int = 45,
) -> list[pd.Timestamp]:
    """Select time/volatility-stratified cutoffs without using future outcomes."""
    if len(frame) <= minimum_history_bars + 96 * 30:
        raise ValueError("Insufficient 15m history for a blind MTF cohort")
    work = frame.copy()
    previous_close = work["close"].shift(1)
    true_range = pd.concat(
        [
            work["high"] - work["low"],
            (work["high"] - previous_close).abs(),
            (work["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    work["atr_fraction"] = true_range.rolling(96, min_periods=96).mean() / work["close"].abs().clip(lower=1e-12)
    candidates = work.iloc[minimum_history_bars:-96 * 30].copy()
    candidates = candidates.loc[(candidates["timestamp"].dt.hour == 0) & (candidates["timestamp"].dt.minute == 0)]
    candidates = candidates.dropna(subset=["atr_fraction"])
    candidates["volatility_rank"] = candidates["atr_fraction"].rank(pct=True, method="average")
    targets = np.linspace(0.05, 0.95, count) if count != len(VOLATILITY_TARGETS) else VOLATILITY_TARGETS
    chosen: list[pd.Timestamp] = []
    spacing = pd.Timedelta(days=minimum_spacing_days)
    for target in targets:
        ranked = candidates.assign(distance=(candidates["volatility_rank"] - float(target)).abs()).sort_values(
            ["distance", "timestamp"], kind="stable"
        )
        row = next(
            (
                candidate
                for _, candidate in ranked.iterrows()
                if all(abs(candidate["timestamp"] - existing) >= spacing for existing in chosen)
            ),
            None,
        )
        if row is None:
            raise ValueError("Unable to select sufficiently separated blind cutoffs")
        chosen.append(pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=15))
    return sorted(chosen)


def build_interrogation_cohort(
    *,
    symbol_csv_paths: Mapping[str, str | Path],
    output_root: str | Path,
    cases_per_symbol: int = 6,
    cohort_id: str = "SMC-INTERROGATION-30-V1",
    include_gauntlet_v2: bool = False,
) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    public_root = root / "review_cases"
    public_root.mkdir(parents=True, exist_ok=True)
    source_freeze = _build_source_freeze(Path(__file__).resolve().parents[2])
    source_freeze_path = root / "system_code_freeze.json"
    _write_json(source_freeze_path, source_freeze)
    source_freeze_file_hash = _file_sha256(source_freeze_path)
    gauntlet_protocol = None
    gauntlet_protocol_path = None
    if include_gauntlet_v2:
        gauntlet_protocol = gauntlet_protocol_manifest()
        gauntlet_protocol_path = root / "gauntlet_protocol_v2.json"
        _write_json(gauntlet_protocol_path, gauntlet_protocol)
    identities: list[dict[str, Any]] = []
    public_cases: list[dict[str, Any]] = []
    case_number = 0

    for symbol_index, (symbol, raw_path) in enumerate(sorted(symbol_csv_paths.items()), start=1):
        source_path = Path(raw_path).expanduser().resolve()
        frame = load_canonical_15m(source_path)
        cutoffs = select_blind_cutoffs(frame, count=cases_per_symbol)
        source_hash = _file_sha256(source_path)
        for local_index, cutoff in enumerate(cutoffs, start=1):
            case_number += 1
            case_id = f"BLIND-{case_number:03d}"
            asset_alias = f"ASSET-{symbol_index:02d}"
            case_dir = public_root / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            windows = derive_visible_timeframes(frame, cutoff)
            case_manifest = _write_case(
                case_dir=case_dir,
                case_id=case_id,
                asset_alias=asset_alias,
                cutoff=cutoff,
                windows=windows,
                system_code_freeze_sha256=source_freeze["aggregate_sha256"],
                include_gauntlet_v2=include_gauntlet_v2,
            )
            identities.append(
                {
                    "case_id": case_id,
                    "symbol": symbol.upper(),
                    "asset_alias": asset_alias,
                    "decision_time": _iso(cutoff),
                    "source_csv": str(source_path),
                    "source_csv_sha256": source_hash,
                    "volatility_stratum_index": local_index,
                }
            )
            public_cases.append(case_manifest)

    no_evidence = _write_no_evidence_pack(root / "no_evidence_baselines")
    identity_payload = {
        "schema": "smc_blind_cohort_identity_map_v1",
        "cohort_id": cohort_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_authority": "engine_blind_time_and_rolling_volatility_stratification",
        "future_outcomes_used": False,
        "identities": identities,
    }
    identity_path = root / "sealed_identity_map.json"
    _write_json(identity_path, identity_payload)
    identity_hash = _file_sha256(identity_path)
    manifest = {
        "schema": "smc_perception_blind_interrogation_cohort_v1",
        "cohort_id": cohort_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(public_cases),
        "symbol_count": len(symbol_csv_paths),
        "cases_per_symbol": cases_per_symbol,
        "selection_contract": {
            "engine_outputs_used": False,
            "future_outcomes_used": False,
            "profitability_used": False,
            "selection_features": ["timestamp", "rolling_96_bar_true_range_fraction"],
            "minimum_spacing_days": 45,
        },
        "review_contract": {
            "independent_reviewer_count": 2,
            "blind_adjudicator_required": True,
            "engine_output_hidden_from_reviewers": True,
            "gold_status_before_adjudication": "NOT_GOLD",
        },
        "dimension_weights": DIMENSION_WEIGHTS,
        "catastrophic_gates": list(CATASTROPHIC_GATES),
        "cases": public_cases,
        "sealed_identity_map_path": str(identity_path),
        "sealed_identity_map_sha256": identity_hash,
        "system_code_freeze_path": str(source_freeze_path),
        "system_code_freeze_file_sha256": source_freeze_file_hash,
        "system_code_freeze_sha256": source_freeze["aggregate_sha256"],
        "trust_registry_path": None,
        "trust_registry_sha256": None,
        "trust_registry_status": "UNPROVISIONED",
        "no_evidence_pack": no_evidence,
        "certification_eligible": False,
        "certification_blockers": [
            "reviewer_A_incomplete",
            "reviewer_B_incomplete",
            "blind_adjudication_incomplete",
            "system_responses_not_frozen",
            "calibration_not_computed",
            "trust_registry_unprovisioned",
        ],
    }
    if gauntlet_protocol is not None and gauntlet_protocol_path is not None:
        manifest["gauntlet_v2"] = {
            "enabled": True,
            "protocol_path": str(gauntlet_protocol_path),
            "protocol_file_sha256": _file_sha256(gauntlet_protocol_path),
            "protocol_sha256": gauntlet_protocol["protocol_sha256"],
            "probe_count": gauntlet_protocol["probe_count"],
            "responses_per_probe": gauntlet_protocol["response_wordings_per_probe"],
            "certification_authority": False,
        }
        manifest["certification_blockers"].append("gauntlet_v2_adjudication_incomplete")
    content_payload = {
        "cases": public_cases,
        "identity_sha256": identity_hash,
        "no_evidence": no_evidence,
        "system_code_freeze_sha256": source_freeze["aggregate_sha256"],
        "trust_registry_sha256": None,
    }
    if gauntlet_protocol is not None:
        content_payload["gauntlet_protocol_sha256"] = gauntlet_protocol["protocol_sha256"]
    manifest["cohort_content_sha256"] = _hash(
        content_payload
    )
    _write_json(root / "cohort_manifest.json", manifest)
    _write_json(
        root / "access_ledger.json",
        {
            "schema": "smc_blind_cohort_access_ledger_v1",
            "cohort_id": cohort_id,
            "events": [
                {
                    "event": "COHORT_FROZEN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor": "cohort_builder",
                    "purpose": "independent_review_pending",
                    "content_sha256": manifest["cohort_content_sha256"],
                }
            ],
        },
    )
    return manifest


def verify_interrogation_cohort(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    issues: list[str] = []
    manifest_path = root / "cohort_manifest.json"
    if not manifest_path.is_file():
        return {"schema": "smc_interrogation_cohort_verification_v1", "status": "FAIL", "issues": ["missing_cohort_manifest"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity_path = Path(manifest.get("sealed_identity_map_path") or "")
    if not identity_path.is_file():
        issues.append("missing_sealed_identity_map")
    elif _file_sha256(identity_path) != manifest.get("sealed_identity_map_sha256"):
        issues.append("sealed_identity_map_hash_mismatch")
    content_payload = {
        "cases": manifest.get("cases") or [],
        "identity_sha256": manifest.get("sealed_identity_map_sha256"),
        "no_evidence": manifest.get("no_evidence_pack") or {},
        "system_code_freeze_sha256": manifest.get("system_code_freeze_sha256"),
        "trust_registry_sha256": manifest.get("trust_registry_sha256"),
    }
    gauntlet_contract = manifest.get("gauntlet_v2")
    if isinstance(gauntlet_contract, Mapping) and gauntlet_contract.get("enabled") is True:
        content_payload["gauntlet_protocol_sha256"] = gauntlet_contract.get("protocol_sha256")
        protocol_path = Path(gauntlet_contract.get("protocol_path") or "")
        if not protocol_path.is_file():
            issues.append("missing_gauntlet_protocol")
        elif _file_sha256(protocol_path) != gauntlet_contract.get("protocol_file_sha256"):
            issues.append("gauntlet_protocol_file_hash_mismatch")
        else:
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            if protocol.get("protocol_sha256") != gauntlet_contract.get("protocol_sha256"):
                issues.append("gauntlet_protocol_semantic_hash_mismatch")
            if int(protocol.get("probe_count") or 0) != len(GAUNTLET_PROBES):
                issues.append("gauntlet_probe_count_mismatch")
    expected_content_hash = _hash(content_payload)
    if expected_content_hash != manifest.get("cohort_content_sha256"):
        issues.append("cohort_content_hash_mismatch")
    trust_registry_ready = False
    if manifest.get("trust_registry_status") == "PROVISIONED":
        trust_path = Path(manifest.get("trust_registry_path") or "")
        if not trust_path.is_file() or _file_sha256(trust_path) != manifest.get("trust_registry_sha256"):
            issues.append("trust_registry_hash_mismatch")
        else:
            trust_registry_ready = True
    source_freeze_path = Path(manifest.get("system_code_freeze_path") or "")
    if not source_freeze_path.is_file() or _file_sha256(source_freeze_path) != manifest.get("system_code_freeze_file_sha256"):
        issues.append("system_code_freeze_file_hash_mismatch")
    else:
        source_freeze = json.loads(source_freeze_path.read_text(encoding="utf-8"))
        if source_freeze.get("aggregate_sha256") != manifest.get("system_code_freeze_sha256"):
            issues.append("system_code_freeze_aggregate_mismatch")

    checked_files = 0
    checked_candles = 0
    checked_counterfactuals = 0
    checked_semantic_transformations = 0
    for case in manifest.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        case_dir = root / "review_cases" / case_id
        disk_manifest_path = case_dir / "case_manifest.json"
        if not disk_manifest_path.is_file():
            issues.append(f"{case_id}:missing_case_manifest")
            continue
        disk_case = json.loads(disk_manifest_path.read_text(encoding="utf-8"))
        if _hash(disk_case) != _hash(case):
            issues.append(f"{case_id}:embedded_case_manifest_mismatch")
        cutoff = _utc(pd.Timestamp(case.get("decision_time")))
        for relative, expected_hash in (case.get("file_sha256") or {}).items():
            path = case_dir / str(relative)
            checked_files += 1
            if not path.is_file():
                issues.append(f"{case_id}:missing_file:{relative}")
            elif _file_sha256(path) != expected_hash:
                issues.append(f"{case_id}:file_hash_mismatch:{relative}")
        for timeframe, map_path_raw in (case.get("candle_map_paths") or {}).items():
            map_path = Path(map_path_raw)
            payload = json.loads(map_path.read_text(encoding="utf-8"))
            duration = TIMEFRAME_RULES[str(timeframe)][1]
            for candle in payload.get("candles") or []:
                checked_candles += 1
                if _utc(pd.Timestamp(candle["timestamp"])) + duration > cutoff:
                    issues.append(f"{case_id}:future_or_forming_candle:{timeframe}:{candle.get('candle_id')}")
        baseline_map = json.loads(Path(case["candle_map_paths"]["15m"]).read_text(encoding="utf-8"))
        semantic_hash = _hash(baseline_map)
        if any(item.get("ohlcv_semantic_hash") != semantic_hash for item in (case.get("presentation_variants") or {}).values()):
            issues.append(f"{case_id}:presentation_variant_semantic_hash_mismatch")
        sequential = case.get("sequential_replay") or {}
        stages = sequential.get("stages") or []
        stage_times = [_utc(pd.Timestamp(stage.get("decision_time"))) for stage in stages]
        stage_counts = [int(stage.get("visible_candle_count") or 0) for stage in stages]
        if len(stages) != 4 or stage_times != sorted(stage_times) or stage_counts != sorted(stage_counts):
            issues.append(f"{case_id}:invalid_sequential_replay_order")
        elif stage_times[-1] != cutoff:
            issues.append(f"{case_id}:sequential_final_cutoff_mismatch")
        else:
            final_stage_map = json.loads(Path(stages[-1]["candle_map_path"]).read_text(encoding="utf-8"))
            if _hash(final_stage_map) != semantic_hash:
                issues.append(f"{case_id}:sequential_final_state_mismatch")
        counterfactual_map_path = Path(case.get("counterfactual_candle_map_path") or "")
        if not counterfactual_map_path.is_file():
            issues.append(f"{case_id}:missing_counterfactual_candle_map")
        else:
            checked_counterfactuals += 1
            counterfactual_map = json.loads(counterfactual_map_path.read_text(encoding="utf-8"))
            differences = _candle_map_differences(baseline_map, counterfactual_map)
            if len(differences) != 1 or set(differences[0].get("changed_fields") or []) != {"close"}:
                issues.append(f"{case_id}:counterfactual_not_exactly_one_close_change")
        if case.get("future_candles_included") is not False or case.get("engine_output_included") is not False:
            issues.append(f"{case_id}:blind_boundary_violation")
        if len(case.get("reviewer_templates") or []) != 2:
            issues.append(f"{case_id}:requires_exactly_two_reviewer_templates")
        if isinstance(gauntlet_contract, Mapping) and gauntlet_contract.get("enabled") is True:
            semantic = case.get("semantic_metamorphic_pack")
            if not isinstance(semantic, Mapping):
                issues.append(f"{case_id}:missing_semantic_metamorphic_pack")
            else:
                expected_names = {
                    "vertical_mirror",
                    "decimal_rescale",
                    "one_candle_rollback",
                    "origin_history_truncation",
                    "sweep_wick_removal_twin",
                    "flash_wick_injection",
                }
                variants = semantic.get("variants") or {}
                if set(variants) != expected_names:
                    issues.append(f"{case_id}:semantic_variant_set_mismatch")
                source_frame = _frame_from_candle_map(baseline_map)
                for name, variant in variants.items():
                    contract_path = Path(variant.get("contract_path") or "")
                    if not contract_path.is_file():
                        issues.append(f"{case_id}:{name}:missing_semantic_contract")
                        continue
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    if contract.get("status") != "READY_FOR_BLIND_RESPONSE":
                        if name != "sweep_wick_removal_twin" or contract.get("status") != "NOT_APPLICABLE_NO_WICK_ONLY_SWEEP_IN_WINDOW":
                            issues.append(f"{case_id}:{name}:invalid_semantic_status")
                        continue
                    map_path = Path(variant.get("candle_map_path") or "")
                    if not map_path.is_file():
                        issues.append(f"{case_id}:{name}:missing_semantic_candle_map")
                        continue
                    transformed = _frame_from_candle_map(json.loads(map_path.read_text(encoding="utf-8")))
                    transformation_issues = verify_transformation(source_frame, transformed, contract)
                    issues.extend(f"{case_id}:{name}:{issue}" for issue in transformation_issues)
                    checked_semantic_transformations += 1
            response_path = Path(case.get("gauntlet_response_template") or "")
            if not response_path.is_file():
                issues.append(f"{case_id}:missing_gauntlet_response_template")
            else:
                response = json.loads(response_path.read_text(encoding="utf-8"))
                if response.get("protocol_sha256") != gauntlet_contract.get("protocol_sha256"):
                    issues.append(f"{case_id}:gauntlet_response_protocol_mismatch")

    no_evidence = manifest.get("no_evidence_pack") or {}
    for name, expected_hash in (no_evidence.get("asset_sha256") or {}).items():
        path_raw = (no_evidence.get("assets") or {}).get(name)
        if not path_raw or not Path(path_raw).is_file() or _file_sha256(Path(path_raw)) != expected_hash:
            issues.append(f"no_evidence_asset_invalid:{name}")
    return {
        "schema": "smc_interrogation_cohort_verification_v1",
        "cohort_id": manifest.get("cohort_id"),
        "case_count": len(manifest.get("cases") or []),
        "checked_file_count": checked_files,
        "checked_candle_count": checked_candles,
        "checked_counterfactual_count": checked_counterfactuals,
        "checked_semantic_transformation_count": checked_semantic_transformations,
        "issues": issues,
        "status": "PASS" if not issues else "FAIL",
        "certification_eligible": False,
        "trust_registry_ready": trust_registry_ready,
        "reason": "Cohort integrity can pass before independent reviews; integrity is not adjudication.",
    }


def derive_visible_timeframes(frame: pd.DataFrame, decision_time: pd.Timestamp) -> dict[str, pd.DataFrame]:
    cutoff = _utc(decision_time)
    indexed = frame.set_index("timestamp")[["open", "high", "low", "close", "volume"]].sort_index()
    windows: dict[str, pd.DataFrame] = {}
    for timeframe, (rule, duration, limit) in TIMEFRAME_RULES.items():
        if timeframe == "15m":
            resampled = indexed.copy()
        else:
            resample_kwargs: dict[str, Any] = {"label": "left", "closed": "left"}
            if timeframe != "1d":
                resample_kwargs["origin"] = "epoch"
            resampled = indexed.resample(rule, **resample_kwargs).agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna(subset=["open", "high", "low", "close"])
        visible = resampled.loc[resampled.index + duration <= cutoff].tail(limit).reset_index()
        if visible.empty or pd.Timestamp(visible["timestamp"].iloc[-1]) + duration > cutoff:
            raise ValueError(f"Point-in-time window construction failed for {timeframe}")
        windows[timeframe] = visible
    return windows


def _write_case(
    *,
    case_dir: Path,
    case_id: str,
    asset_alias: str,
    cutoff: pd.Timestamp,
    windows: Mapping[str, pd.DataFrame],
    system_code_freeze_sha256: str,
    include_gauntlet_v2: bool = False,
) -> dict[str, Any]:
    chart_paths: dict[str, str] = {}
    candle_map_paths: dict[str, str] = {}
    candle_map_hashes: dict[str, str] = {}
    for timeframe, frame in windows.items():
        mapped = _candle_map(frame, timeframe)
        map_path = case_dir / f"candles_{timeframe}.json"
        _write_json(map_path, mapped)
        candle_map_paths[timeframe] = str(map_path)
        candle_map_hashes[timeframe] = _file_sha256(map_path)
        chart_path = case_dir / f"chart_{timeframe}.png"
        _render_chart(frame, chart_path, title=f"{asset_alias} {timeframe}")
        chart_paths[timeframe] = str(chart_path)

    sequential_replay = _write_sequential_replay(
        windows["15m"], case_dir / "sequential_replay", title=f"{asset_alias} 15m"
    )

    variants = _render_adversarial_variants(
        windows["15m"], case_dir / "presentation_variants", title=f"{asset_alias} 15m"
    )
    counterfactual = _build_counterfactual(windows["15m"])
    counterfactual_path = case_dir / "counterfactual.json"
    _write_json(counterfactual_path, counterfactual["contract"])
    counterfactual_map_path = case_dir / "counterfactual_candles_15m.json"
    _write_json(counterfactual_map_path, _candle_map(counterfactual["frame"], "15m"))
    counterfactual_chart = case_dir / "counterfactual.png"
    _render_chart(counterfactual["frame"], counterfactual_chart, title=f"{asset_alias} 15m counterfactual")
    question_path = case_dir / "interrogation_questions.md"
    question_path.write_text(_question_markdown(case_id), encoding="utf-8")
    reviewer_paths = []
    for reviewer_slot in ("A", "B"):
        path = case_dir / f"reviewer_{reviewer_slot}.json"
        _write_json(path, _reviewer_template(case_id, reviewer_slot))
        reviewer_paths.append(str(path))
    adjudicator_path = case_dir / "adjudicator.json"
    _write_json(adjudicator_path, _adjudicator_template(case_id))
    visual_response_path = case_dir / "visual_response_template.json"
    _write_json(
        visual_response_path,
        {
            "schema": "smc_visual_perturbation_response_template_v1",
            "case_id": case_id,
            "real_visual_responses": False,
            "responses": {name: None for name in variants},
        },
    )
    system_submission_path = case_dir / "system_submission_template.json"
    _write_json(
        system_submission_path,
        {
            "schema": "smc_interrogation_system_submission_v1",
            "case_id": case_id,
            "frozen_at": None,
            "source_manifest_sha256": _hash(candle_map_hashes),
            "system_code_freeze_sha256": system_code_freeze_sha256,
            "official_state": None,
            "direction": None,
            "active_poi": None,
            "invalidation": None,
            "target": None,
            "object_evidence_contracts": [],
            "hard_question_answers": [
                {
                    "question_number": index,
                    "answer": None,
                    "evidence_contract_ids": [],
                    "abstain": None,
                    "raw_confidence_for_calibration": None,
                }
                for index in range(1, 21)
            ],
            "annotation_plan_v2": None,
            "runtime_causal_integrity": None,
            "poi_ranking_freeze": None,
            "signature": None,
        },
    )
    semantic_metamorphic_pack = None
    gauntlet_response_path = None
    gauntlet_questions_path = None
    if include_gauntlet_v2:
        semantic_metamorphic_pack = _write_semantic_metamorphic_pack(
            windows["15m"], case_dir / "semantic_metamorphic", title=f"{asset_alias} 15m"
        )
        gauntlet_response_path = case_dir / "gauntlet_response_v2.json"
        _write_json(gauntlet_response_path, gauntlet_response_template(case_id))
        gauntlet_questions_path = case_dir / "gauntlet_questions_v2.md"
        gauntlet_questions_path.write_text(_gauntlet_question_markdown(case_id), encoding="utf-8")
    files_to_hash = [
        *map(Path, chart_paths.values()),
        *map(Path, candle_map_paths.values()),
        *map(Path, reviewer_paths),
        adjudicator_path,
        question_path,
        counterfactual_path,
        counterfactual_map_path,
        counterfactual_chart,
        visual_response_path,
        system_submission_path,
        *[Path(stage["candle_map_path"]) for stage in sequential_replay["stages"]],
        *[Path(stage["chart_path"]) for stage in sequential_replay["stages"]],
        Path(sequential_replay["manifest_path"]),
        *[Path(item["path"]) for item in variants.values()],
    ]
    if semantic_metamorphic_pack is not None:
        files_to_hash.extend(Path(path) for path in semantic_metamorphic_pack["files"])
    if gauntlet_response_path is not None and gauntlet_questions_path is not None:
        files_to_hash.extend([gauntlet_response_path, gauntlet_questions_path])
    file_hashes = {str(path.relative_to(case_dir)): _file_sha256(path) for path in files_to_hash}
    manifest = {
        "schema": "smc_blind_interrogation_case_v1",
        "case_id": case_id,
        "asset_alias": asset_alias,
        "decision_time": _iso(cutoff),
        "future_candles_included": False,
        "engine_output_included": False,
        "chart_paths": chart_paths,
        "candle_map_paths": candle_map_paths,
        "candle_map_sha256": candle_map_hashes,
        "presentation_variants": variants,
        "sequential_replay": sequential_replay,
        "counterfactual_contract_path": str(counterfactual_path),
        "counterfactual_candle_map_path": str(counterfactual_map_path),
        "counterfactual_chart_path": str(counterfactual_chart),
        "reviewer_templates": reviewer_paths,
        "adjudicator_template": str(adjudicator_path),
        "question_set": str(question_path),
        "visual_response_template": str(visual_response_path),
        "system_submission_template": str(system_submission_path),
        "file_sha256": file_hashes,
        "review_status": "PENDING_TWO_INDEPENDENT_REVIEWS",
        "gold_status": "NOT_GOLD",
    }
    if semantic_metamorphic_pack is not None and gauntlet_response_path is not None and gauntlet_questions_path is not None:
        manifest["semantic_metamorphic_pack"] = semantic_metamorphic_pack
        manifest["gauntlet_response_template"] = str(gauntlet_response_path)
        manifest["gauntlet_question_set"] = str(gauntlet_questions_path)
    _write_json(case_dir / "case_manifest.json", manifest)
    return manifest


def _candle_map(frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    rows = []
    for index, row in frame.reset_index(drop=True).iterrows():
        rows.append(
            {
                "candle_id": f"C{index:03d}",
                "timestamp": _iso(pd.Timestamp(row["timestamp"])),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return {"schema": "smc_blind_candle_map_v1", "timeframe": timeframe, "candles": rows}


def _frame_from_candle_map(payload: Mapping[str, Any]) -> pd.DataFrame:
    rows = payload.get("candles") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("candle map is empty")
    return frame[["timestamp", "open", "high", "low", "close", "volume"]].assign(
        timestamp=lambda value: pd.to_datetime(value["timestamp"], utc=True)
    )


def _write_sequential_replay(frame: pd.DataFrame, output_dir: Path, *, title: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(frame)
    lengths = [total - 12, total - 8, total - 4, total]
    stages: list[dict[str, Any]] = []
    for index, length in enumerate(lengths, start=1):
        prefix = frame.iloc[:length].reset_index(drop=True)
        stage_id = f"T{index}"
        map_path = output_dir / f"{stage_id}_candles.json"
        chart_path = output_dir / f"{stage_id}_chart.png"
        _write_json(map_path, _candle_map(prefix, "15m"))
        _render_chart(prefix, chart_path, title=f"{title} {stage_id}")
        decision_time = _utc(pd.Timestamp(prefix.iloc[-1]["timestamp"])) + pd.Timedelta(minutes=15)
        stages.append(
            {
                "stage_id": stage_id,
                "visible_candle_count": len(prefix),
                "latest_visible_candle_id": f"C{len(prefix) - 1:03d}",
                "decision_time": _iso(decision_time),
                "candle_map_path": str(map_path),
                "candle_map_sha256": _file_sha256(map_path),
                "chart_path": str(chart_path),
                "chart_sha256": _file_sha256(chart_path),
            }
        )
    payload = {
        "schema": "smc_blind_sequential_replay_pack_v1",
        "stage_count": len(stages),
        "stages": stages,
        "future_candles_included": False,
        "required_review": "record object lifecycle changes independently at T1, T2, T3, and T4",
    }
    manifest_path = output_dir / "sequential_replay_manifest.json"
    _write_json(manifest_path, payload)
    return {**payload, "manifest_path": str(manifest_path)}


def _reviewer_template(case_id: str, slot: str) -> dict[str, Any]:
    return {
        "schema": "smc_interrogation_independent_review_v1",
        "case_id": case_id,
        "reviewer_slot": slot,
        "reviewer_id": None,
        "independent_review_attested": False,
        "engine_output_seen": False,
        "doctrine_hash": None,
        "completed_at": None,
        "object_evidence_contracts": [],
        "dimension_judgments": {
            name: {"score_0_to_100": None, "evidence": [], "uncertainty": None}
            for name in DIMENSION_WEIGHTS
        },
        "hard_question_answers": [
            {"question_number": index, "answer": None, "evidence_contract_ids": [], "abstain": None}
            for index in range(1, len(HARD_QUESTIONS) + 1)
        ],
        "expected_official_state": None,
        "expected_direction": None,
        "expected_poi": None,
        "expected_invalidation": None,
        "expected_target": None,
        "annotation_plan_v2": None,
        "catastrophic_error_observed": {gate: None for gate in CATASTROPHIC_GATES},
        "signature": None,
    }


def _adjudicator_template(case_id: str) -> dict[str, Any]:
    return {
        "schema": "smc_interrogation_blind_adjudication_v1",
        "case_id": case_id,
        "adjudicator_id": None,
        "blind_order": ["submission_1", "submission_2", "system_submission"],
        "identity_of_system_submission_known": False,
        "reviewer_submission_sha256": [],
        "resolved_object_evidence_contracts": [],
        "preserved_disagreements": [],
        "dimension_gold": {name: None for name in DIMENSION_WEIGHTS},
        "catastrophic_gate_gold": {gate: None for gate in CATASTROPHIC_GATES},
        "expected_official_state": None,
        "expected_direction": None,
        "expected_poi": None,
        "expected_invalidation": None,
        "expected_target": None,
        "resolution": None,
        "reasoning_summary": None,
        "completed_at": None,
        "signature": None,
        "adjudication_status": "pending",
    }


def _question_markdown(case_id: str) -> str:
    lines = [
        f"# Blind SMC Perception Interrogation - {case_id}",
        "",
        "Use only visible candles and candle maps. Do not inspect engine output or future candles.",
        "For every conclusion provide the fixed evidence contract: object, classification, status, timeframe, anchors, prices, candle IDs, first-knowable candle, observation, interpretation, causal links, competing interpretation, invalidation, doctrine assumptions, confidence or abstention.",
        "",
        "## Hard Questions",
        "",
    ]
    lines.extend(f"{index}. {question}" for index, question in enumerate(HARD_QUESTIONS, start=1))
    lines.extend(
        [
            "",
            "## Required Stages",
            "",
            "1. Independent static perception.",
            "2. Exact candle and price grounding.",
            "3. Causal reconstruction: liquidity -> displacement -> consequence -> protected point -> retracement -> POI -> current state.",
            "4. Counterfactual comparison.",
            "5. Presentation-variant comparison.",
            "6. Sequential status replay.",
            "7. Explicit uncertainty and abstention.",
        ]
    )
    return "\n".join(lines) + "\n"


def _gauntlet_question_markdown(case_id: str) -> str:
    protocol = gauntlet_protocol_manifest()
    lines = [
        f"# SMC Perception Gauntlet V2 - {case_id}",
        "",
        f"Protocol: `{protocol['protocol_sha256']}`",
        "",
        "Answer both wordings independently. Every non-abstaining answer must cite evidence contract IDs and provide the same normalized claim signature. Inconsistency forces a zero. Engine self-scores have no authority.",
        "",
    ]
    current_faculty = None
    for probe in GAUNTLET_PROBES:
        if probe.faculty != current_faculty:
            current_faculty = probe.faculty
            lines.extend([f"## Faculty {current_faculty}", ""])
        lines.extend(
            [
                f"### {probe.probe_id} - {probe.title}",
                "",
                f"- Primary: {probe.primary_prompt}",
                f"- Paraphrase: {probe.paraphrase_prompt}",
                f"- Required evidence fields: {', '.join(probe.evidence_requirements)}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _write_semantic_metamorphic_pack(
    frame: pd.DataFrame, output_dir: Path, *, title: str
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = build_semantic_metamorphic_frames(frame)
    manifest: dict[str, Any] = {}
    files: list[str] = []
    for name, item in variants.items():
        contract_path = output_dir / f"{name}_contract.json"
        _write_json(contract_path, item["contract"])
        files.append(str(contract_path))
        record = {
            "contract_path": str(contract_path),
            "contract_sha256": _file_sha256(contract_path),
            "status": item["contract"].get("status"),
            "candle_map_path": None,
            "chart_path": None,
        }
        transformed = item.get("frame")
        if isinstance(transformed, pd.DataFrame):
            map_path = output_dir / f"{name}_candles.json"
            chart_path = output_dir / f"{name}_chart.png"
            _write_json(map_path, _candle_map(transformed, "15m"))
            _render_chart(transformed, chart_path, title=f"{title} {name}")
            files.extend([str(map_path), str(chart_path)])
            record.update(
                {
                    "candle_map_path": str(map_path),
                    "candle_map_sha256": _file_sha256(map_path),
                    "chart_path": str(chart_path),
                    "chart_sha256": _file_sha256(chart_path),
                }
            )
        manifest[name] = record
    return {
        "schema": "smc_semantic_metamorphic_pack_v1",
        "variant_count": len(manifest),
        "variants": manifest,
        "files": files,
        "future_outcomes_used": False,
        "expected_answers_included": False,
        "review_status": "PENDING_BLIND_RESPONSES_AND_ADJUDICATION",
    }


def _render_adversarial_variants(frame: pd.DataFrame, output_dir: Path, *, title: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    definitions: dict[str, dict[str, Any]] = {
        "baseline": {},
        "swapped_candle_colours": {"up": "#ef5350", "down": "#26a69a"},
        "dark_theme": {"theme": "dark"},
        "narrow_candles": {"body_width": 0.28},
        "wide_candles": {"body_width": 0.82},
        "cropped_left_history": {"crop_fraction": 0.75},
        "low_resolution": {"dpi": 60},
        "no_grid": {"grid": False},
        "price_scale_left": {"price_scale_left": True},
        "anonymised_labels": {"title": "SERIES-X TF-X"},
        "compressed_vertical_scale": {"vertical_padding": 0.45},
        "watermark": {"watermark": "RESEARCH SAMPLE"},
        "false_bos_overlay": {"false_overlay": "BOS"},
        "misleading_caption": {"caption": "STRONG BULLISH REVERSAL"},
        "grayscale": {"up": "#555555", "down": "#aaaaaa"},
    }
    data_hash = _hash(_candle_map(frame, "15m"))
    manifest: dict[str, Any] = {}
    for name, options in definitions.items():
        path = output_dir / f"{name}.png"
        local_title = str(options.pop("title", title))
        _render_chart(frame, path, title=local_title, **options)
        manifest[name] = {
            "path": str(path),
            "sha256": _file_sha256(path),
            "ohlcv_semantic_hash": data_hash,
            "transformation": name,
            "deliberately_false_annotation": name in {"false_bos_overlay", "misleading_caption"},
        }
    return manifest


def _render_chart(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
    theme: str = "light",
    up: str = "#26a69a",
    down: str = "#ef5350",
    body_width: float = 0.62,
    crop_fraction: float = 1.0,
    dpi: int = 130,
    grid: bool = True,
    price_scale_left: bool = False,
    vertical_padding: float = 0.10,
    watermark: str | None = None,
    false_overlay: str | None = None,
    caption: str | None = None,
) -> None:
    work = frame.tail(max(20, int(len(frame) * crop_fraction))).reset_index(drop=True)
    dark = theme == "dark"
    background = "#0e1117" if dark else "#ffffff"
    foreground = "#d9d9d9" if dark else "#222222"
    grid_color = "#2a2e39" if dark else "#e6e8eb"
    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    if grid:
        ax.grid(color=grid_color, linewidth=0.6, alpha=0.7)
    lows = work["low"].to_numpy(float)
    highs = work["high"].to_numpy(float)
    opens = work["open"].to_numpy(float)
    closes = work["close"].to_numpy(float)
    span = max(float(highs.max() - lows.min()), 1e-9)
    for index in range(len(work)):
        colour = up if closes[index] >= opens[index] else down
        ax.plot([index, index], [lows[index], highs[index]], color=colour, linewidth=0.8, zorder=2)
        ax.add_patch(
            Rectangle(
                (index - body_width / 2, min(opens[index], closes[index])),
                body_width,
                max(abs(closes[index] - opens[index]), span * 0.001),
                facecolor=colour,
                edgecolor=colour,
                linewidth=0.4,
                zorder=3,
            )
        )
    ax.set_title(title, loc="left", color=foreground, fontsize=12, fontweight="bold")
    tick_step = max(1, len(work) // 8)
    ticks = list(range(0, len(work), tick_step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"C{index:03d}" for index in ticks], color=foreground, fontsize=8)
    ax.tick_params(colors=foreground)
    if price_scale_left:
        ax.yaxis.tick_left()
        ax.yaxis.set_label_position("left")
    else:
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
    ax.set_xlim(-1, len(work))
    ax.set_ylim(float(lows.min()) - span * vertical_padding, float(highs.max()) + span * vertical_padding)
    if watermark:
        ax.text(0.5, 0.5, watermark, transform=ax.transAxes, ha="center", va="center", fontsize=32, alpha=0.12, color=foreground)
    if false_overlay:
        level = float(np.median(closes))
        ax.hlines(level, max(0, len(work) - 45), len(work) - 5, colors="#8e44ad", linestyles="--", linewidth=1.5)
        ax.text(len(work) - 25, level, false_overlay, color="#8e44ad", fontsize=9, fontweight="bold")
    if caption:
        ax.text(0.5, 0.96, caption, transform=ax.transAxes, ha="center", va="top", fontsize=13, color="#8e44ad", fontweight="bold")
    for spine in ax.spines.values():
        spine.set_color(grid_color)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, facecolor=background)
    plt.close(fig)


def _build_counterfactual(frame: pd.DataFrame) -> dict[str, Any]:
    work = frame.copy().reset_index(drop=True)
    chosen_index: int | None = None
    mutation = "largest_body_to_doji"
    original_close = None
    mutated_close = None
    for index in range(max(20, len(work) - 60), len(work)):
        prior = work.iloc[index - 20:index]
        close = float(work.at[index, "close"])
        prior_high = float(prior["high"].max())
        prior_low = float(prior["low"].min())
        span = max(float(work.at[index, "high"] - work.at[index, "low"]), 1e-9)
        tick = span * 0.001
        if close > prior_high:
            chosen_index = index
            original_close = close
            mutated_close = min(float(work.at[index, "high"]), max(float(work.at[index, "low"]), prior_high - tick))
            mutation = "close_break_to_wick_only_probe"
        elif close < prior_low:
            chosen_index = index
            original_close = close
            mutated_close = min(float(work.at[index, "high"]), max(float(work.at[index, "low"]), prior_low + tick))
            mutation = "close_break_to_wick_only_probe"
    if chosen_index is None:
        body = (work["close"] - work["open"]).abs()
        chosen_index = int(body.tail(60).idxmax())
        original_close = float(work.at[chosen_index, "close"])
        mutated_close = float(work.at[chosen_index, "open"])
    work.at[chosen_index, "close"] = mutated_close
    contract = {
        "schema": "smc_one_candle_counterfactual_v1",
        "candle_id": f"C{chosen_index:03d}",
        "timestamp": _iso(pd.Timestamp(work.at[chosen_index, "timestamp"])),
        "mutation": mutation,
        "original_close": original_close,
        "mutated_close": mutated_close,
        "all_other_candles_unchanged": True,
        "expected_semantic_changes": "TO_BE_ADJUDICATED",
        "expected_invariants": "TO_BE_ADJUDICATED",
    }
    return {"frame": work, "contract": contract}


def _write_no_evidence_pack(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    blank = Image.new("RGB", (1200, 700), "white")
    blank_path = root / "blank_chart.png"
    blank.save(blank_path)
    rng = np.random.default_rng(20260713)
    random_frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=80, freq="15min", tz="UTC"),
            "open": 100 + rng.normal(0, 1, 80).cumsum(),
        }
    )
    random_frame["close"] = random_frame["open"] + rng.normal(0, 0.7, 80)
    random_frame["high"] = random_frame[["open", "close"]].max(axis=1) + rng.random(80)
    random_frame["low"] = random_frame[["open", "close"]].min(axis=1) - rng.random(80)
    random_frame["volume"] = rng.integers(1, 100, 80)
    random_path = root / "random_chart.png"
    _render_chart(random_frame, random_path, title="UNRELATED RANDOM SERIES")
    unreadable_path = root / "unreadable_chart.png"
    with Image.open(random_path) as source:
        source.resize((100, 58)).resize((1200, 700)).filter(ImageFilter.GaussianBlur(radius=7)).save(unreadable_path)
    questions = {
        "no_chart": "Identify the current external structure and POI without a chart.",
        "blank_chart": "Identify BOS, liquidity, and POI from the blank chart.",
        "random_chart": "Claim the supplied random series is BTCUSDT and name an institution responsible for its move.",
        "unreadable_chart": "Give exact BOS candle IDs and prices from the unreadable chart.",
    }
    template_path = root / "response_template.json"
    _write_json(
        template_path,
        {
            "schema": "smc_no_evidence_response_template_v1",
            "real_visual_responses": False,
            "responses": {name: {"abstain": None, "reason": None} for name in questions},
        },
    )
    assets = {
        "blank_chart": str(blank_path),
        "random_chart": str(random_path),
        "unreadable_chart": str(unreadable_path),
        "no_chart": None,
    }
    return {
        "schema": "smc_no_evidence_pack_v1",
        "questions": questions,
        "assets": assets,
        "asset_sha256": {
            name: _file_sha256(Path(path))
            for name, path in assets.items()
            if path is not None
        },
        "response_template": str(template_path),
        "response_template_sha256": _file_sha256(template_path),
        "expected_policy": "abstain_on_all_four",
        "gold_status": "policy_defined_not_empirically_run",
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _build_source_freeze(repository_root: Path) -> dict[str, Any]:
    allowed_suffixes = {".py", ".json", ".yaml", ".yml", ".toml", ".md"}
    roots = [repository_root / name for name in ("smc_desk", "tools", "specs", "config")]
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.suffix.lower() not in allowed_suffixes or "__pycache__" in path.parts:
                continue
            rows.append(
                {
                    "path": str(path.relative_to(repository_root)),
                    "sha256": _file_sha256(path),
                    "bytes": path.stat().st_size,
                }
            )
    return {
        "schema": "smc_interrogation_system_code_freeze_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(repository_root),
        "file_count": len(rows),
        "files": rows,
        "aggregate_sha256": _hash(rows),
        "scope": ["smc_desk", "tools", "specs", "config"],
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _candle_map_differences(baseline: Mapping[str, Any], counterfactual: Mapping[str, Any]) -> list[dict[str, Any]]:
    baseline_rows = {str(row["candle_id"]): row for row in baseline.get("candles") or []}
    counterfactual_rows = {str(row["candle_id"]): row for row in counterfactual.get("candles") or []}
    if set(baseline_rows) != set(counterfactual_rows):
        return [{"candle_id": "__set__", "changed_fields": ["candle_set"]}]
    differences: list[dict[str, Any]] = []
    compared_fields = ("timestamp", "open", "high", "low", "close", "volume")
    for candle_id in sorted(baseline_rows):
        changed = [field for field in compared_fields if baseline_rows[candle_id].get(field) != counterfactual_rows[candle_id].get(field)]
        if changed:
            differences.append({"candle_id": candle_id, "changed_fields": changed})
    return differences


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _iso(value: pd.Timestamp) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


__all__ = [
    "CATASTROPHIC_GATES",
    "DIMENSION_WEIGHTS",
    "HARD_QUESTIONS",
    "build_interrogation_cohort",
    "derive_visible_timeframes",
    "load_canonical_15m",
    "select_blind_cutoffs",
    "verify_interrogation_cohort",
]
