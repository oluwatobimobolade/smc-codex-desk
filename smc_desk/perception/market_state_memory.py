"""Cross-run market-state memory (observe-only).

``build_market_state`` derives where a setup has got to for one run, and
``diff_states`` can say what changed between two states -- but nothing ever
persisted the previous state, so every run started with amnesia. A colleague
is expected to remember what it believed last time and to name the difference:
liquidity taken while it was not watching, a bias flip, a new primary POI,
advance or regression along the trader sequence.

This module is the small durable store that closes that loop.

Boundaries, deliberately:

* The transition record lives **beside** the evidence pack, never inside it.
  ``pack_hash`` must remain a pure function of the sealed evidence; history
  must not change it.
* Memory is fail-soft. A missing or corrupt store is recorded as a note and
  the run continues; memory problems must never fail an analysis run.
* Observe-only. The record carries ``signal_allowed: False`` and grants no
  entry, sizing, paper, or live authority.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from smc_desk.perception.market_state import MarketState, diff_states

SCHEMA = "market_state_transition_v1"
STORE_SCHEMA = "market_state_memory_store_v1"
STORE_DIRNAME = "market_state_store"


def store_path(output_root: Path | str, symbol: str) -> Path:
    """Durable per-symbol state file, kept with the run outputs (runtime data)."""
    return Path(output_root).expanduser().resolve() / STORE_DIRNAME / f"{symbol.upper()}.json"


def market_state_from_dict(payload: Mapping[str, Any]) -> MarketState:
    """Rebuild a ``MarketState`` from its ``to_dict`` (evidence-pack) form.

    Only the fields ``diff_states`` and a reader actually use are restored;
    unknown or missing groups degrade to the same defaults a fresh state has.
    """
    if not isinstance(payload, Mapping):
        return MarketState()
    context = payload.get("context") if isinstance(payload.get("context"), Mapping) else {}
    structure = payload.get("structure") if isinstance(payload.get("structure"), Mapping) else {}
    liquidity = payload.get("liquidity") if isinstance(payload.get("liquidity"), Mapping) else {}
    poi = payload.get("poi") if isinstance(payload.get("poi"), Mapping) else {}
    confirmation = (
        payload.get("confirmation") if isinstance(payload.get("confirmation"), Mapping) else {}
    )
    return MarketState(
        symbol=str(payload.get("symbol") or ""),
        decision_time=str(payload.get("decision_time") or ""),
        state=str(payload.get("state") or "NO_CONTEXT"),
        context_timeframe=context.get("timeframe") or None,
        bias=str(context.get("bias") or "unknown"),
        narrative_state=context.get("narrative_state") or None,
        price_location=str(context.get("price_location") or "unknown"),
        current_price=_f(context.get("current_price")),
        range_high=_f(structure.get("range_high")),
        range_low=_f(structure.get("range_low")),
        equilibrium=_f(structure.get("equilibrium")),
        protected_high=_f(structure.get("protected_high")),
        protected_low=_f(structure.get("protected_low")),
        draw_price=_f(liquidity.get("draw_price")),
        draw_kind=liquidity.get("draw_kind") or None,
        swept_liquidity_ids=tuple(str(x) for x in (liquidity.get("swept_ids") or []) if x),
        unswept_liquidity_ids=tuple(str(x) for x in (liquidity.get("unswept_ids") or []) if x),
        primary_poi_id=poi.get("primary_id") or None,
        primary_poi_low=_f(poi.get("primary_low")),
        primary_poi_high=_f(poi.get("primary_high")),
        alternate_poi_ids=tuple(str(x) for x in (poi.get("alternates") or []) if x),
        poi_arrival_time=confirmation.get("poi_arrival_time") or None,
        confirmation_timeframe=confirmation.get("timeframe") or None,
        confirmation_sweep_id=confirmation.get("sweep_id") or None,
        confirmation_break_id=confirmation.get("break_id") or None,
        entry_model=confirmation.get("entry_model") or None,
        entry_price=_f(confirmation.get("entry_price")),
        waiting_for=str(payload.get("waiting_for") or ""),
        invalidation=str(payload.get("invalidation") or ""),
        reasons=tuple(str(x) for x in (payload.get("reasons") or []) if x),
    )


def load_previous_state(path: Path) -> tuple[MarketState | None, str]:
    """Read the stored state. Returns ``(state, note)``; never raises."""
    if not path.exists():
        return None, "no stored state; first recorded observation for this symbol"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"stored state unreadable ({type(exc).__name__}); treated as first observation"
    if not isinstance(payload, Mapping) or not isinstance(payload.get("market_state"), Mapping):
        return None, "stored state malformed; treated as first observation"
    return market_state_from_dict(payload["market_state"]), ""


def save_current_state(path: Path, market_state: Mapping[str, Any]) -> None:
    """Persist the current state atomically so a crash cannot tear the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "schema": STORE_SCHEMA,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "market_state": dict(market_state),
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(envelope, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp_path, path)


def record_run_transition(
    *,
    output_root: Path | str,
    symbol: str,
    current_market_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Diff the current state against the stored one and persist the current.

    Returns the transition record (also written into the run package by the
    caller). Any memory-layer failure is returned as a note, never raised.
    """
    recorded_at = datetime.now(timezone.utc).isoformat()
    path = store_path(output_root, symbol)
    notes: list[str] = []
    previous: MarketState | None = None
    try:
        previous, note = load_previous_state(path)
        if note:
            notes.append(note)
    except Exception as exc:  # noqa: BLE001 -- memory must never fail a run
        notes.append(f"memory load failed ({type(exc).__name__}); treated as first observation")
        previous = None

    current = market_state_from_dict(current_market_state)
    transition = diff_states(previous, current)

    try:
        save_current_state(path, current_market_state)
    except OSError as exc:
        notes.append(f"memory save failed ({type(exc).__name__}); transition recorded but not stored")

    return {
        "schema": SCHEMA,
        "symbol": symbol.upper(),
        "recorded_at": recorded_at,
        "store_path": str(path),
        "transition": transition.to_dict(),
        "notes": notes,
        "authority": "observe_only_colleague_memory",
        "signal_allowed": False,
    }


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "SCHEMA",
    "STORE_SCHEMA",
    "load_previous_state",
    "market_state_from_dict",
    "record_run_transition",
    "save_current_state",
    "store_path",
]
