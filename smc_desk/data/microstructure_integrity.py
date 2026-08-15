"""Fail-closed market-event integrity and immutable evidence batches."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from smc_desk.data.hashing import canonical_json, file_sha256, object_sha256, sha256_text
from smc_desk.data.schemas import (
    BookLevel,
    IntegrityState,
    OrderBookDelta,
    OrderBookSnapshot,
    SequenceIntegrityCertificate,
)


class SequencedOrderBook:
    """Reconstruct an L2 book while refusing gaps, duplicates, and stale state.

    The sequence rules follow the common snapshot-plus-delta contract used by
    Binance-style streams.  Once a gap occurs the object remains FAILED until
    a caller explicitly supplies a new snapshot; no downstream mechanism claim
    may treat its book as current.
    """

    def __init__(self, *, venue: str, instrument: str):
        self.venue = venue
        self.instrument = instrument
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.snapshot_sequence: int | None = None
        self.last_sequence: int | None = None
        self.first_sequence: int | None = None
        self.event_count = 0
        self.gap_count = 0
        self.duplicate_count = 0
        self.out_of_order_count = 0
        self.state = IntegrityState.FAILED
        self.reason_codes: list[str] = ["snapshot_required"]

    @property
    def resynchronization_required(self) -> bool:
        return self.state == IntegrityState.FAILED

    def bootstrap(self, snapshot: OrderBookSnapshot) -> None:
        self._assert_identity(snapshot.venue, snapshot.instrument)
        self.bids = _levels(snapshot.bids)
        self.asks = _levels(snapshot.asks)
        self.snapshot_sequence = snapshot.last_update_id
        self.last_sequence = snapshot.last_update_id
        self.first_sequence = None
        self.event_count = 0
        self.gap_count = 0
        self.duplicate_count = 0
        self.out_of_order_count = 0
        self.state = IntegrityState.COMPLETE
        self.reason_codes = []

    def apply(self, delta: OrderBookDelta) -> bool:
        self._assert_identity(delta.venue, delta.instrument)
        if self.snapshot_sequence is None or self.state == IntegrityState.FAILED:
            self._fail("snapshot_or_resynchronization_required")
            return False
        if delta.final_update_id <= self.snapshot_sequence:
            self.duplicate_count += 1
            return False
        if self.last_sequence is not None and delta.final_update_id <= self.last_sequence:
            self.duplicate_count += 1
            self._degrade("duplicate_or_stale_delta")
            return False

        expected = int(self.last_sequence) + 1
        if delta.previous_final_update_id is not None:
            continuous = delta.previous_final_update_id == self.last_sequence
        else:
            continuous = delta.first_update_id <= expected <= delta.final_update_id
        if not continuous:
            if delta.first_update_id > expected or (
                delta.previous_final_update_id is not None
                and delta.previous_final_update_id > int(self.last_sequence)
            ):
                self.gap_count += 1
                self._fail("sequence_gap")
            else:
                self.out_of_order_count += 1
                self._fail("out_of_order_delta")
            return False

        _apply_levels(self.bids, delta.bids)
        _apply_levels(self.asks, delta.asks)
        self.last_sequence = delta.final_update_id
        self.first_sequence = self.first_sequence or delta.first_update_id
        self.event_count += 1
        return True

    def top_of_book(self) -> dict[str, str | None]:
        if self.state == IntegrityState.FAILED:
            return {"bid": None, "ask": None, "state": self.state.value}
        bid = max(self.bids) if self.bids else None
        ask = min(self.asks) if self.asks else None
        if bid is not None and ask is not None and bid >= ask:
            self._fail("crossed_or_locked_book")
            return {"bid": None, "ask": None, "state": self.state.value}
        return {
            "bid": None if bid is None else _number(bid),
            "ask": None if ask is None else _number(ask),
            "state": self.state.value,
        }

    def certificate(self, *, source_batch_sha256: str | None = None) -> SequenceIntegrityCertificate:
        return SequenceIntegrityCertificate(
            venue=self.venue,
            instrument=self.instrument,
            stream_kind="order_book_delta",
            state=self.state,
            checked_at=datetime.now(timezone.utc),
            snapshot_sequence=self.snapshot_sequence,
            first_sequence=self.first_sequence,
            last_sequence=self.last_sequence,
            event_count=self.event_count,
            gap_count=self.gap_count,
            duplicate_count=self.duplicate_count,
            out_of_order_count=self.out_of_order_count,
            resynchronization_required=self.resynchronization_required,
            reason_codes=sorted(set(self.reason_codes)),
            source_batch_sha256=source_batch_sha256,
        )

    def _assert_identity(self, venue: str, instrument: str) -> None:
        if venue != self.venue or instrument != self.instrument:
            raise ValueError(
                f"Order-book identity mismatch: expected {self.venue}/{self.instrument}, "
                f"got {venue}/{instrument}"
            )

    def _degrade(self, reason: str) -> None:
        if self.state != IntegrityState.FAILED:
            self.state = IntegrityState.DEGRADED
        self.reason_codes.append(reason)

    def _fail(self, reason: str) -> None:
        self.state = IntegrityState.FAILED
        self.reason_codes.append(reason)


def write_immutable_event_batch(
    output_dir: str | Path,
    *,
    events: Iterable[Mapping[str, Any] | Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal canonical JSONL and a hash chain into a never-overwritten folder."""
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite immutable event batch: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = [_event_payload(event) for event in events]
    chain = "0" * 64
    records: list[dict[str, Any]] = []
    lines: list[str] = []
    for index, event in enumerate(normalized):
        event_sha = object_sha256(event)
        chain = sha256_text(f"{chain}:{event_sha}")
        records.append({"index": index, "event_sha256": event_sha, "chain_sha256": chain})
        lines.append(canonical_json(event))
    manifest = {
        "schema": "immutable_market_event_batch_v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event_count": len(normalized),
        "metadata": dict(metadata),
        "event_records": records,
        "terminal_chain_sha256": chain,
        "authority_contract": {
            "observed_evidence_only": True,
            "mechanism_authority": False,
            "forecast_authority": False,
            "signal_allowed": False,
        },
    }
    manifest["manifest_sha256"] = object_sha256(manifest)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        events_path = staging / "events.jsonl"
        manifest_path = staging / "manifest.json"
        events_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for path in (events_path, manifest_path):
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        os.replace(staging, target)
    except Exception:
        for child in staging.glob("*"):
            child.unlink(missing_ok=True)
        staging.rmdir()
        raise
    return {
        **manifest,
        "events_file_sha256": file_sha256(target / "events.jsonl"),
        "manifest_file_sha256": file_sha256(target / "manifest.json"),
    }


def verify_immutable_event_batch(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest_hash = manifest.pop("manifest_sha256", None)
    lines = (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    chain = "0" * 64
    records = []
    for index, event in enumerate(events):
        event_sha = object_sha256(event)
        chain = sha256_text(f"{chain}:{event_sha}")
        records.append({"index": index, "event_sha256": event_sha, "chain_sha256": chain})
    passed = (
        expected_manifest_hash == object_sha256(manifest)
        and manifest.get("event_count") == len(events)
        and manifest.get("event_records") == records
        and manifest.get("terminal_chain_sha256") == chain
    )
    return {
        "schema": "immutable_market_event_batch_verification_v1",
        "status": "PASS" if passed else "FAIL",
        "event_count": len(events),
        "terminal_chain_sha256": chain,
    }


def _event_payload(event: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    if isinstance(event, Mapping):
        return dict(event)
    raise TypeError(f"Unsupported market event type: {type(event).__name__}")


def _levels(levels: Iterable[BookLevel]) -> dict[Decimal, Decimal]:
    return {level.price: level.quantity for level in levels if level.quantity > 0}


def _apply_levels(book: dict[Decimal, Decimal], levels: Iterable[BookLevel]) -> None:
    for level in levels:
        if level.quantity == 0:
            book.pop(level.price, None)
        else:
            book[level.price] = level.quantity


def _number(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


__all__ = [
    "SequencedOrderBook",
    "verify_immutable_event_batch",
    "write_immutable_event_batch",
]
