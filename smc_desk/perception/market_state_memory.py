"""Cross-run market-state memory (observe-only).

The sealed evidence pack describes one observation.  This module remembers the
last *comparable* observation and records what changed.  Comparability is a
strict contract: the same symbol from a different venue, provider instrument,
or market type is not the same market, and an observation whose time cannot be
ordered must never replace trusted memory.

Memory remains deliberately subordinate:

* history lives beside, never inside, the sealed evidence pack;
* failures are disclosed but never fail the analysis run;
* no transition grants signal, sizing, paper, or live authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from smc_desk.perception.market_state import MarketState, diff_states

try:  # POSIX production runtime; the fallback keeps read-only tooling importable.
    import fcntl
except ImportError:  # pragma: no cover - Windows is not a supported live runner.
    fcntl = None  # type: ignore[assignment]


SCHEMA = "market_state_transition_v2"
STORE_SCHEMA = "market_state_memory_store_v2"
LEGACY_STORE_SCHEMA = "market_state_memory_store_v1"
STORE_DIRNAME = "market_state_store"
IDENTITY_FIELDS = (
    "canonical_symbol",
    "source",
    "provider_symbol",
    "market_type",
    "timeframe_profile",
)


def normalize_market_identity(
    symbol: str,
    market_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable fields that make two market observations comparable."""
    raw = market_identity if isinstance(market_identity, Mapping) else {}
    canonical_symbol = str(raw.get("canonical_symbol") or symbol).upper()
    provider_symbol = str(raw.get("provider_symbol") or canonical_symbol).upper()
    profile = raw.get("timeframe_profile")
    if isinstance(profile, str):
        timeframes = tuple(sorted({part.strip() for part in profile.split(",") if part.strip()}))
    elif isinstance(profile, (list, tuple, set)):
        timeframes = tuple(sorted({str(item) for item in profile if item}))
    else:
        timeframes = ()
    return {
        "canonical_symbol": canonical_symbol,
        "source": str(raw.get("source") or "unspecified").lower(),
        "provider_symbol": provider_symbol,
        "market_type": str(raw.get("market_type") or "unspecified").lower(),
        "timeframe_profile": list(timeframes),
    }


def market_identity_hash(identity: Mapping[str, Any]) -> str:
    """Stable identity fingerprint used in the store filename and envelope."""
    payload = {field: identity.get(field) for field in IDENTITY_FIELDS}
    return _fingerprint(payload)


def store_path(
    output_root: Path | str,
    symbol: str,
    market_identity: Mapping[str, Any] | None = None,
) -> Path:
    """Durable state path, source-scoped when identity evidence is available."""
    root = Path(output_root).expanduser().resolve() / STORE_DIRNAME
    canonical = symbol.upper()
    if market_identity is None:
        # Backward-compatible path for direct callers.  The live runner always
        # supplies source identity and therefore uses the scoped path below.
        return root / f"{canonical}.json"
    identity = normalize_market_identity(canonical, market_identity)
    return root / f"{canonical}--{market_identity_hash(identity)[:16]}.json"


def market_state_from_dict(payload: Mapping[str, Any]) -> MarketState:
    """Rebuild the fields used by ``diff_states`` from pack/store JSON."""
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
    """Read a store for diagnostics/backward compatibility; never raises."""
    state, _, note, _ = _load_store_record(path)
    return state, note


def save_current_state(
    path: Path,
    market_state: Mapping[str, Any],
    *,
    market_identity: Mapping[str, Any] | None = None,
    evidence_fingerprint: str | None = None,
) -> None:
    """Persist a state with atomic replacement and crash-safe file flushing."""
    symbol = str(market_state.get("symbol") or "").upper()
    identity = normalize_market_identity(symbol, market_identity)
    envelope = {
        "schema": STORE_SCHEMA,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "market_identity": identity,
        "market_identity_hash": market_identity_hash(identity),
        "evidence_fingerprint": evidence_fingerprint,
        "state_fingerprint": _fingerprint(market_state),
        "market_state": dict(market_state),
    }
    _atomic_write_json(path, envelope)


def record_run_transition(
    *,
    output_root: Path | str,
    symbol: str,
    current_market_state: Mapping[str, Any],
    market_identity: Mapping[str, Any] | None = None,
    evidence_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Diff and conditionally persist one source-bound market observation.

    The read/compare/write decision is protected by a per-store process lock.
    A store is updated only for a parseable first observation or a strictly
    newer observation.  Equal-time identical states are re-observations and do
    not rewrite the store.  Older, conflicting, or unverifiably ordered states
    are descriptive artifacts only.
    """
    canonical_symbol = symbol.upper()
    identity = normalize_market_identity(canonical_symbol, market_identity)
    identity_digest = market_identity_hash(identity)
    path = store_path(output_root, canonical_symbol, market_identity)
    lock_path = path.with_suffix(path.suffix + ".lock")
    recorded_at = datetime.now(timezone.utc).isoformat()
    notes: list[str] = []
    previous: MarketState | None = None
    previous_meta: dict[str, Any] = {}
    load_status = "not_attempted"
    store_status = "not_updated"
    store_updated = False
    forward = False

    current = market_state_from_dict(current_market_state)
    current_state_fingerprint = _fingerprint(current_market_state)

    try:
        with _store_lock(lock_path):
            previous, previous_meta, note, load_status = _load_store_record(
                path,
                expected_symbol=canonical_symbol,
                expected_identity_hash=identity_digest if market_identity is not None else None,
            )
            if note:
                notes.append(note)

            current_dt = _parse_dt(current.decision_time)
            previous_dt = _parse_dt(previous.decision_time) if previous is not None else None
            current_symbol_matches = current.symbol.upper() == canonical_symbol

            protected_load_failure = load_status in {
                "unsupported_schema",
                "identity_mismatch",
                "symbol_mismatch",
            }
            if not current_symbol_matches:
                store_status = "rejected_current_symbol_mismatch"
                notes.append(
                    f"current market_state symbol {current.symbol or '<missing>'!r} does not match "
                    f"requested symbol {canonical_symbol!r}; store was NOT updated"
                )
            elif protected_load_failure:
                store_status = f"preserved_{load_status}"
                notes.append("existing store identity/schema could not be trusted; store was NOT updated")
            elif current_dt is None:
                store_status = "preserved_unverifiable_current_time"
                notes.append(
                    "current decision time is missing or unparseable; diff is descriptive only "
                    "and the store was NOT updated"
                )
            elif previous is None:
                save_current_state(
                    path,
                    current_market_state,
                    market_identity=identity,
                    evidence_fingerprint=evidence_fingerprint,
                )
                store_updated = True
                forward = True
                store_status = (
                    "created"
                    if load_status == "missing"
                    else "recovered_unreadable_store"
                )
            elif previous_dt is None:
                store_status = "preserved_unverifiable_previous_time"
                notes.append(
                    "stored decision time is missing or unparseable; order cannot be proven, "
                    "so the diff is descriptive only and the store was NOT updated"
                )
            elif previous_dt > current_dt:
                store_status = "preserved_newer_state"
                notes.append(
                    "stored state is from a LATER decision time "
                    f"({previous.decision_time} > {current.decision_time}); this run is a "
                    "historical replay, so the diff is descriptive only and the store was NOT updated"
                )
            elif previous_dt == current_dt:
                same_state = previous_meta.get("state_fingerprint") == current_state_fingerprint
                previous_evidence = previous_meta.get("evidence_fingerprint")
                evidence_agrees = (
                    not previous_evidence
                    or not evidence_fingerprint
                    or previous_evidence == evidence_fingerprint
                )
                if same_state and evidence_agrees:
                    forward = True
                    store_status = "reobserved_equal_unchanged"
                    notes.append(
                        "equal decision time and identical state; treated as a sealed re-observation "
                        "without rewriting the store"
                    )
                else:
                    store_status = "preserved_equal_time_conflict"
                    notes.append(
                        "equal decision time carried conflicting state or evidence; diff is "
                        "descriptive only and the store was NOT updated"
                    )
            else:
                save_current_state(
                    path,
                    current_market_state,
                    market_identity=identity,
                    evidence_fingerprint=evidence_fingerprint,
                )
                store_updated = True
                forward = True
                store_status = "updated"
    except OSError as exc:
        store_status = "save_or_lock_failed"
        notes.append(
            f"memory store operation failed ({type(exc).__name__}); transition recorded but not stored"
        )
    except Exception as exc:  # noqa: BLE001 -- memory must never fail a run
        store_status = "memory_operation_failed"
        notes.append(
            f"memory operation failed ({type(exc).__name__}); transition recorded but not stored"
        )

    transition = diff_states(previous, current)
    return {
        "schema": SCHEMA,
        "symbol": canonical_symbol,
        "recorded_at": recorded_at,
        "store_path": str(path),
        "lock_path": str(lock_path),
        "store_status": store_status,
        "store_updated": store_updated,
        "load_status": load_status,
        "market_identity": identity,
        "market_identity_hash": identity_digest,
        "evidence_fingerprint": evidence_fingerprint,
        "previous_evidence_fingerprint": previous_meta.get("evidence_fingerprint"),
        "current_state_fingerprint": current_state_fingerprint,
        "previous_state_fingerprint": previous_meta.get("state_fingerprint"),
        "previous_decision_time": previous.decision_time if previous is not None else None,
        "current_decision_time": current.decision_time,
        "forward_transition": forward,
        "transition": transition.to_dict(),
        "notes": notes,
        "authority": "observe_only_colleague_memory",
        "signal_allowed": False,
    }


def _load_store_record(
    path: Path,
    *,
    expected_symbol: str | None = None,
    expected_identity_hash: str | None = None,
) -> tuple[MarketState | None, dict[str, Any], str, str]:
    if not path.exists():
        return None, {}, "no stored state; first recorded observation for this market identity", "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return (
            None,
            {},
            f"stored state unreadable ({type(exc).__name__}); eligible for source-bound recovery",
            "unreadable",
        )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("market_state"), Mapping):
        return None, {}, "stored state malformed; eligible for source-bound recovery", "malformed"
    schema = payload.get("schema")
    if schema not in {STORE_SCHEMA, LEGACY_STORE_SCHEMA}:
        return None, {}, f"unsupported stored-state schema {schema!r}", "unsupported_schema"

    raw_state = payload["market_state"]
    state = market_state_from_dict(raw_state)
    if expected_symbol and state.symbol.upper() != expected_symbol.upper():
        return (
            None,
            dict(payload),
            f"stored symbol {state.symbol or '<missing>'!r} does not match {expected_symbol!r}",
            "symbol_mismatch",
        )
    stored_identity_hash = payload.get("market_identity_hash")
    if expected_identity_hash and stored_identity_hash != expected_identity_hash:
        return (
            None,
            dict(payload),
            "stored market identity does not match the current provider instrument",
            "identity_mismatch",
        )
    meta = dict(payload)
    meta["state_fingerprint"] = str(
        payload.get("state_fingerprint") or _fingerprint(raw_state)
    )
    note = ""
    if schema == LEGACY_STORE_SCHEMA:
        note = "legacy unscoped memory store loaded; source identity is not certified"
    return state, meta, note, "ok"


@contextmanager
def _store_lock(lock_path: Path) -> Iterator[None]:
    """Serialize read/compare/write so concurrent runners cannot regress state."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:  # pragma: no cover - filesystem-specific durability fallback
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - not every filesystem supports dir fsync
        pass
    finally:
        os.close(fd)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


__all__ = [
    "IDENTITY_FIELDS",
    "LEGACY_STORE_SCHEMA",
    "SCHEMA",
    "STORE_SCHEMA",
    "load_previous_state",
    "market_identity_hash",
    "market_state_from_dict",
    "normalize_market_identity",
    "record_run_transition",
    "save_current_state",
    "store_path",
]
