"""Sealed deterministic perception experiment envelope (BR-001 to BR-003)."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from smc_desk.brain.structure_reasoning_roles import build_ai_role_trace
from smc_desk.colleague.run_context import dataframe_to_candles
from smc_desk.data.hashing import (
    dataframe_sha256,
    file_sha256,
    object_sha256,
    source_tree_manifest,
)
from smc_desk.data.market_truth_certificate import certify_market_truth
from smc_desk.data.ohlcv_contract import (
    OHLCV_COLUMNS,
    as_utc_naive,
    load_ohlcv_csv,
    validate_canonical_15m,
)
from smc_desk.perception.config import (
    DEFAULT_DETECTOR_CONFIG_PATH,
    detector_config_metadata,
    load_perception_config,
)
from smc_desk.perception.engine_v2 import PerceptionEngineV2


SCHEMA = "perception_experiment_envelope_v1"
DEFAULT_SEED = 1729
TIMEFRAMES = ("15m", "1h", "4h", "1d")
EXACT_DEPENDENCIES = (
    "pandas",
    "numpy",
    "matplotlib",
    "mplfinance",
    "Pillow",
    "pydantic",
    "fastapi",
    "plotly",
    "opencv-python",
    "requests",
    "PyYAML",
    "pytest",
)


def run_deterministic_baseline(
    *,
    symbol: str,
    source: str | Path,
    decision_time: str | pd.Timestamp | None,
    output_dir: str | Path,
    window_15m: int = 3000,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Run a reproducible detector baseline without AI or annotation promotion."""
    random.seed(seed)
    np.random.seed(seed)
    root = Path(__file__).resolve().parents[2]
    source_path = Path(source).expanduser().resolve()
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    source_df = validate_canonical_15m(load_ohlcv_csv(source_path))
    decision = _resolve_decision_time(source_df, decision_time)
    selected = _select_experiment_window(source_df, decision, window_15m)
    selection_hash = dataframe_sha256(selected, columns=OHLCV_COLUMNS)
    dataset_id = f"{_normalize_symbol(symbol)}_15m_{selection_hash[:16]}"
    truth = certify_market_truth(
        selected,
        symbol=symbol,
        decision_time=decision,
        dataset_id=dataset_id,
        observed_symbol=symbol,
    )

    source_manifest = _build_source_manifest(root)
    environment_manifest = _environment_manifest(root, seed)
    input_manifest = _input_manifest(
        source_path=source_path,
        source_df=source_df,
        selected_df=selected,
        truth=truth.certificate,
        source_manifest=source_manifest,
    )
    ai_trace = build_ai_role_trace(
        provider="NONE",
        model="NONE",
        role_status="NOT_INVOKED_BASELINE",
    )
    perception_result = _run_perception(
        symbol=_normalize_symbol(symbol),
        timeframe_dfs=truth.timeframe_dfs,
        decision_time=decision,
    )
    annotation_plan = {
        "schema": "annotation_plan_v2",
        "status": "NOT_RUN_PRE_STRUCTURE_BASELINE",
        "objects": [],
        "trade_box": None,
        "reason": "Annotation is downstream of validated semantic structure; baseline does not invent it.",
    }
    authority_trace = {
        "schema": "perception_authority_trace_v1",
        "authority_order": [
            "market_truth_certificate",
            "detector_candidate_geometry",
            "formal_graph_and_human_doctrine_when_available",
            "ai_semantic_reasoning",
            "annotation",
        ],
        "canonical_detector": "smc_desk.perception.engine_v2.PerceptionEngineV2",
        "detector_config": detector_config_metadata(),
        "legacy_engine_loaded": "smc_desk.engine" in sys.modules,
        "legacy_rules_loaded": "smc_desk.rules" in sys.modules,
        "forbidden_legacy_modules_loaded": [
            name
            for name in (
                "smc_desk.engine",
                "smc_desk.rules",
                "smc_desk.mtf",
                "smc_desk.case_library",
            )
            if name in sys.modules
        ],
        "ai_invoked": False,
        "signal_allowed": False,
        "paper_execution": "disabled",
        "live_execution": "disabled",
    }

    _write_json(out / "source_manifest.json", source_manifest)
    _write_json(out / "environment_manifest.json", environment_manifest)
    _write_json(out / "input_manifest.json", input_manifest)
    _write_json(out / "market_truth_certificate.json", truth.certificate)
    _write_json(out / "authority_trace.json", authority_trace)
    _write_json(out / "ai_trace.json", ai_trace)
    _write_json(out / "perception_result.json", perception_result)
    _write_json(out / "annotation_plan.json", annotation_plan)
    for timeframe, frame in truth.timeframe_dfs.items():
        frame.to_csv(out / f"certified_{timeframe}.csv", index=False)

    validation_summary = _validation_summary(
        truth.certificate,
        perception_result,
        authority_trace,
        ai_trace,
        environment_manifest,
    )
    _write_json(out / "validation_summary.json", validation_summary)
    output_hashes = {
        path.name: file_sha256(path)
        for path in sorted(out.iterdir())
        if path.is_file() and path.name != "run_manifest.json"
    }
    experiment_fingerprint = object_sha256(
        {
            "schema": SCHEMA,
            "source_manifest_sha256": source_manifest["manifest_sha256"],
            "environment_sha256": environment_manifest["environment_sha256"],
            "dataset_selection_sha256": selection_hash,
            "decision_time": truth.certificate["decision_time"],
            "detector_config_sha256": file_sha256(DEFAULT_DETECTOR_CONFIG_PATH),
            "seed": seed,
            "perception_result_sha256": output_hashes["perception_result.json"],
        }
    )
    run_manifest = {
        "schema": SCHEMA,
        "run_kind": "DETERMINISTIC_PERCEPTION_BASELINE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "experiment_fingerprint": experiment_fingerprint,
        "repo_head": _git_head(root),
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "environment_sha256": environment_manifest["environment_sha256"],
        "dataset_id": dataset_id,
        "dataset_selection_sha256": selection_hash,
        "decision_time": truth.certificate["decision_time"],
        "detector_version": "PerceptionEngineV2",
        "detector_config_sha256": file_sha256(DEFAULT_DETECTOR_CONFIG_PATH),
        "doctrine_version": "PRE_ESPP_CONSTITUTION_NOT_FROZEN",
        "ai_provider": "NONE",
        "ai_model": "NONE",
        "prompt_template_sha256": None,
        "image_hashes": {},
        "ai_raw_response_sha256": None,
        "ai_parsed_response_sha256": None,
        "critic_result": "NOT_RUN",
        "human_review_status": "NOT_STARTED",
        "annotation_plan_sha256": output_hashes["annotation_plan.json"],
        "rendered_image_sha256": None,
        "evaluation_result": "NOT_EVALUATED_NO_ADJUDICATED_GOLD",
        "random_seed": seed,
        "output_hashes": output_hashes,
        "observe_only": True,
        "signal_allowed": False,
    }
    run_manifest["manifest_sha256"] = object_sha256(run_manifest)
    _write_json(out / "run_manifest.json", run_manifest)
    return run_manifest


def _run_perception(
    *,
    symbol: str,
    timeframe_dfs: dict[str, pd.DataFrame],
    decision_time: pd.Timestamp,
) -> dict[str, Any]:
    config = load_perception_config()
    snapshots: dict[str, Any] = {}
    input_windows: dict[str, Any] = {}
    for timeframe in TIMEFRAMES:
        frame = timeframe_dfs[timeframe]
        detector_frame = frame.tail(config.lookback_bars).reset_index(drop=True)
        if detector_frame.empty:
            snapshots[timeframe] = {"status": "INSUFFICIENT_DATA", "snapshot": None}
            input_windows[timeframe] = {"rows": 0, "start": None, "end": None}
            continue
        candles = dataframe_to_candles(
            detector_frame,
            venue="BINANCE_USD_M",
            instrument=symbol,
            timeframe=timeframe,
            reference_time=_aware(decision_time),
        )
        snapshot = PerceptionEngineV2(
            expected_instrument=symbol,
            expected_timeframe=timeframe,
            config=config,
        ).analyze(candles, _aware(decision_time))
        snapshots[timeframe] = {
            "status": "PASS",
            "snapshot": snapshot.model_dump(mode="json"),
        }
        input_windows[timeframe] = {
            "rows": int(len(detector_frame)),
            "start": _iso(detector_frame["timestamp"].iloc[0]),
            "end": _iso(detector_frame["timestamp"].iloc[-1]),
            "sha256": dataframe_sha256(detector_frame, columns=OHLCV_COLUMNS),
        }
    payload = {
        "schema": "deterministic_perception_baseline_v1",
        "symbol": symbol,
        "decision_time": _iso(decision_time),
        "detector_config": config.model_dump(mode="json"),
        "input_windows": input_windows,
        "timeframes": snapshots,
        "predictive_claim": False,
        "accuracy_claim": False,
    }
    payload["result_sha256"] = object_sha256(payload)
    return payload


def _select_experiment_window(
    source_df: pd.DataFrame,
    decision: pd.Timestamp,
    window_15m: int,
) -> pd.DataFrame:
    if window_15m < 96:
        raise ValueError("window_15m must be at least 96 rows.")
    close_times = source_df["timestamp"] + pd.Timedelta(minutes=15)
    visible_indices = source_df.index[close_times <= decision]
    if len(visible_indices) == 0:
        raise ValueError("No closed source rows at decision time.")
    last_visible = int(visible_indices[-1])
    start = max(0, last_visible - window_15m + 1)
    end = min(len(source_df), last_visible + 11)
    return source_df.iloc[start:end].reset_index(drop=True)


def _input_manifest(
    *,
    source_path: Path,
    source_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    truth: dict[str, Any],
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "perception_input_manifest_v1",
        "source_csv": str(source_path),
        "source_csv_sha256": file_sha256(source_path),
        "source_csv_rows": int(len(source_df)),
        "selected_rows": int(len(selected_df)),
        "selected_rows_sha256": dataframe_sha256(selected_df, columns=OHLCV_COLUMNS),
        "dataset_id": truth["dataset_id"],
        "decision_time": truth["decision_time"],
        "future_rows_excluded": truth["future_rows_excluded"],
        "timeframe_hashes": truth["timeframe_hashes"],
        "timeframe_rows": truth["timeframe_rows"],
        "source_manifest_sha256": source_manifest["manifest_sha256"],
    }


def _environment_manifest(root: Path, seed: int) -> dict[str, Any]:
    lock_path = root / "requirements-perception.lock"
    dependencies = {
        name: importlib.metadata.version(name)
        for name in EXACT_DEPENDENCIES
    }
    locked = {
        line.split("==", 1)[0]: line.split("==", 1)[1]
        for raw in lock_path.read_text(encoding="utf-8").splitlines()
        if (line := raw.strip()) and not line.startswith("#") and "==" in line
    }
    lock_matches_environment = all(locked.get(name) == version for name, version in dependencies.items())
    stable = {
        "supported_python": "3.14.5",
        "actual_python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "requirements_lock_sha256": file_sha256(lock_path),
        "lock_matches_environment": lock_matches_environment,
        "random_seed": seed,
    }
    return {
        "schema": "perception_environment_manifest_v1",
        **stable,
        "environment_sha256": object_sha256(stable),
    }


def _build_source_manifest(root: Path) -> dict[str, Any]:
    files: list[Path] = []
    for directory in (
        root / "smc_desk" / "data",
        root / "smc_desk" / "perception",
        root / "smc_desk" / "brain",
        root / "smc_desk" / "research",
    ):
        files.extend(directory.rglob("*.py"))
    files.extend(
        [
            root / "smc_desk" / "colleague" / "run_context.py",
            root / "tools" / "run_perception_experiment.py",
            root / "specs" / "PERCEPTION_DETECTOR_CONFIG_V2.yaml",
            root / "specs" / "AI_CENTERED_STRUCTURE_REASONING_V1.yaml",
            root / "requirements-perception.lock",
            root / "pyproject.toml",
        ]
    )
    return source_tree_manifest(root, files)


def _validation_summary(
    truth: dict[str, Any],
    perception: dict[str, Any],
    authority: dict[str, Any],
    ai_trace: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "market_truth_pass": truth.get("status") == "PASS",
        "partial_htf_excluded": truth.get("invariants", {}).get("partial_htf_candles_excluded") is True,
        "all_htf_has_lineage": truth.get("invariants", {}).get("every_htf_bar_has_exact_15m_lineage") is True,
        "detector_result_hashed": bool(perception.get("result_sha256")),
        "legacy_authority_absent": (
            authority.get("legacy_engine_loaded") is False
            and authority.get("legacy_rules_loaded") is False
            and authority.get("forbidden_legacy_modules_loaded") == []
        ),
        "ai_role_contract_recorded": ai_trace.get("schema") == "ai_structure_role_trace_v1",
        "supported_python_matches": environment.get("actual_python") == environment.get("supported_python"),
        "dependency_lock_matches": environment.get("lock_matches_environment") is True,
        "trade_promotion_disabled": authority.get("signal_allowed") is False,
    }
    return {
        "schema": "perception_validation_summary_v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "ground_truth_status": "NOT_EVALUATED_NO_ADJUDICATED_GOLD",
        "readiness_gate": "NOT_PASSED_BR004_BR006_PENDING",
    }


def _resolve_decision_time(frame: pd.DataFrame, value: str | pd.Timestamp | None) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp(frame["timestamp"].iloc[-1]) + pd.Timedelta(minutes=15)
    return as_utc_naive(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return "unknown"


def _normalize_symbol(value: str) -> str:
    return value.upper().replace("/", "").replace("-", "").replace(".P", "")


def _aware(value: pd.Timestamp) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def _iso(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")
