from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from smc_desk.case_library import file_sha256
from smc_desk.colleague.run_context import TIMEFRAME_DURATIONS, load_local_15m


RESOLUTION_VERSION = "0.1"


def _as_utc_naive(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def _price_values(values: list[Any]) -> list[float]:
    prices: list[float] = []
    for value in values:
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            raw = value.get("price") or value.get("level") or value.get("target")
        else:
            raw = value
        if raw is None or raw == "":
            continue
        prices.append(float(raw))
    return prices


def _terminal_hit(
    *,
    row: pd.Series,
    direction: str,
    target_prices: list[float],
    invalidation_prices: list[float],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    high = float(row["high"])
    low = float(row["low"])
    timestamp = pd.Timestamp(row["timestamp"]).isoformat()
    if direction == "bullish":
        for price in target_prices:
            if high >= price:
                hits.append({"type": "target_touch", "price": price, "timestamp": timestamp})
        for price in invalidation_prices:
            if low <= price:
                hits.append({"type": "invalidation", "price": price, "timestamp": timestamp})
    elif direction == "bearish":
        for price in target_prices:
            if low <= price:
                hits.append({"type": "target_touch", "price": price, "timestamp": timestamp})
        for price in invalidation_prices:
            if high >= price:
                hits.append({"type": "invalidation", "price": price, "timestamp": timestamp})
    return hits


def _is_hypothetical_signal(decision_action: str | None) -> bool:
    return str(decision_action or "").upper() == "PAPER_EXECUTE_DISABLED"


def _status_for_event(status: str, decision_action: str | None) -> str:
    if _is_hypothetical_signal(decision_action):
        return status
    return f"observed_{status}_no_trade"


def _favorable(value: bool | None, decision_action: str | None) -> bool | None:
    return value if _is_hypothetical_signal(decision_action) else None


def _resolve_scenario(scenario: dict[str, Any], future_window: pd.DataFrame, decision_action: str | None) -> dict[str, Any]:
    terminal = scenario.get("terminal_conditions") or {}
    direction = str(scenario.get("direction") or "").lower()
    target_prices = _price_values(list(terminal.get("target_touch") or []))
    invalidation_prices = _price_values(list(terminal.get("invalidation") or []))
    base = {
        "scenario_id": scenario.get("scenario_id"),
        "direction": direction,
        "setup_stage": scenario.get("setup_stage"),
        "target_prices": target_prices,
        "invalidation_prices": invalidation_prices,
        "performance_claim_allowed": False,
    }
    if direction not in {"bullish", "bearish"}:
        return base | {"status": "unsupported_direction", "terminal_event": None, "hypothetically_favorable": None}
    if not target_prices and not invalidation_prices:
        return base | {"status": "no_terminal_conditions", "terminal_event": None, "hypothetically_favorable": None}

    for _, row in future_window.iterrows():
        hits = _terminal_hit(
            row=row,
            direction=direction,
            target_prices=target_prices,
            invalidation_prices=invalidation_prices,
        )
        if not hits:
            continue
        hit_types = {hit["type"] for hit in hits}
        if hit_types == {"target_touch"}:
            event = sorted(hits, key=lambda item: item["price"], reverse=direction == "bearish")[0]
            return base | {
                "status": _status_for_event("target_touched_first", decision_action),
                "terminal_event": event,
                "hypothetically_favorable": _favorable(True, decision_action),
            }
        if hit_types == {"invalidation"}:
            event = sorted(hits, key=lambda item: item["price"], reverse=direction == "bullish")[0]
            return base | {
                "status": _status_for_event("invalidated_first", decision_action),
                "terminal_event": event,
                "hypothetically_favorable": _favorable(False, decision_action),
            }
        return base | {
            "status": _status_for_event("ambiguous_same_candle", decision_action),
            "terminal_event": {"type": "target_and_invalidation_same_candle", "hits": hits, "timestamp": hits[0]["timestamp"]},
            "hypothetically_favorable": None,
        }

    return base | {
        "status": _status_for_event("expired_no_terminal_touch", decision_action),
        "terminal_event": None,
        "hypothetically_favorable": None,
    }


def _resolution_status(decision_action: str | None, complete_window: bool) -> str:
    if not complete_window:
        return "unresolved_waiting_for_future_candles"
    action = str(decision_action or "").upper()
    if action == "PAPER_EXECUTE_DISABLED":
        return "resolved_hypothetical_disabled_signal"
    if action == "WATCH":
        return "resolved_watch_observation"
    if action == "SOURCE_MISMATCH":
        return "resolved_source_mismatch_no_trade"
    return "resolved_no_setup_observation"


def resolve_outcome_contract(
    *,
    contract: dict[str, Any],
    ohlcv: pd.DataFrame,
    source_path: Path | None = None,
    run_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision_available_at = _as_utc_naive(contract["decision_available_at"])
    resolution_due_at = _as_utc_naive(contract["resolution_due_at"])
    horizon_bars = int(contract.get("horizon_bars_15m") or 96)
    df = ohlcv.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
    df = df.sort_values("timestamp").reset_index(drop=True)
    future_window = df.loc[(df["timestamp"] >= decision_available_at) & (df["timestamp"] < resolution_due_at)].reset_index(drop=True)
    last_required_open = resolution_due_at - TIMEFRAME_DURATIONS["15m"]
    complete_window = bool(
        len(future_window) >= horizon_bars
        and not future_window.empty
        and pd.Timestamp(future_window["timestamp"].iloc[-1]) >= last_required_open
    )
    source_meta = None
    if source_path is not None:
        source_meta = {
            "path": str(source_path.expanduser().resolve()),
            "sha256": file_sha256(source_path.expanduser()) if source_path.expanduser().exists() else None,
        }

    scenario_results = (
        []
        if not complete_window
        else [
            _resolve_scenario(scenario, future_window, contract.get("decision_action"))
            for scenario in contract.get("tracked_scenarios", [])
        ]
    )
    terminal_counts: dict[str, int] = {}
    for result in scenario_results:
        terminal_counts[result["status"]] = terminal_counts.get(result["status"], 0) + 1

    available_until = None
    if not future_window.empty:
        available_until = pd.Timestamp(future_window["timestamp"].iloc[-1]).isoformat()
    resolution = {
        "outcome_resolution_version": RESOLUTION_VERSION,
        "outcome_contract_version": contract.get("outcome_contract_version"),
        "status": _resolution_status(contract.get("decision_action"), complete_window),
        "symbol": contract.get("symbol"),
        "decision_action": contract.get("decision_action"),
        "decision_available_at": decision_available_at.isoformat(),
        "resolution_due_at": resolution_due_at.isoformat(),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "authority": "research_observation_only",
        "market_edge_claimed": False,
        "paper_execution_enabled": False,
        "live_execution_enabled": False,
        "source": source_meta,
        "run_manifest": run_manifest,
        "future_window": {
            "first_candle_open": None if future_window.empty else pd.Timestamp(future_window["timestamp"].iloc[0]).isoformat(),
            "last_candle_open": available_until,
            "available_bars": int(len(future_window)),
            "required_bars": horizon_bars,
            "needed_until": last_required_open.isoformat(),
            "complete_window": complete_window,
        },
        "scenario_results": scenario_results,
        "aggregate": {
            "tracked_scenarios": len(contract.get("tracked_scenarios", [])),
            "resolved_scenarios": len(scenario_results),
            "terminal_counts": terminal_counts,
            "performance_claim_allowed": False,
            "reason": "No edge or win-rate claim is allowed from one disabled/live-shadow observation.",
        },
    }
    if not complete_window:
        resolution["unresolved_reason"] = "Future OHLCV has not reached the contract resolution window."
    return resolution


def resolve_run_outcome(
    *,
    run_dir: Path,
    ohlcv_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    pending_path = run_dir / "outcome" / "pending.json"
    if not pending_path.exists():
        raise FileNotFoundError(f"Missing pending outcome contract: {pending_path}")
    contract = json.loads(pending_path.read_text(encoding="utf-8"))
    manifest_path = run_dir / "run_manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if ohlcv_path is None:
        source_manifest_path = run_dir / "source_manifest.json"
        if not source_manifest_path.exists():
            raise FileNotFoundError("No --ohlcv supplied and source_manifest.json is missing.")
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        ohlcv_path = Path(str(source_manifest["source_path"]))
    ohlcv_path = ohlcv_path.expanduser().resolve()
    resolution = resolve_outcome_contract(
        contract=contract,
        ohlcv=load_local_15m(ohlcv_path),
        source_path=ohlcv_path,
        run_manifest=None
        if run_manifest is None
        else {
            "path": str(manifest_path),
            "sha256": file_sha256(manifest_path),
            "run_id": run_manifest.get("run_id"),
            "decision_candle_open": run_manifest.get("decision_candle_open"),
        },
    )
    target = output_path.expanduser().resolve() if output_path else run_dir / "outcome" / "resolution.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(resolution, indent=2, default=str), encoding="utf-8")
    return resolution
