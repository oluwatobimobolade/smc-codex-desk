from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from smc_desk.data.microstructure_integrity import (
    SequencedOrderBook,
    verify_immutable_event_batch,
    write_immutable_event_batch,
)
from smc_desk.data.schemas import BookLevel, IntegrityState, OrderBookDelta, OrderBookSnapshot


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        venue="binance", instrument="ETHUSDT", captured_at=NOW, last_update_id=100,
        bids=[BookLevel(price=Decimal("99"), quantity=Decimal("3"))],
        asks=[BookLevel(price=Decimal("101"), quantity=Decimal("4"))],
        data_source="test",
    )


def _delta(first: int, final: int, *, previous: int | None = None) -> OrderBookDelta:
    return OrderBookDelta(
        venue="binance", instrument="ETHUSDT", event_time=NOW, receive_time=NOW,
        first_update_id=first, final_update_id=final, previous_final_update_id=previous,
        bids=[BookLevel(price=Decimal("100"), quantity=Decimal("2"))],
        asks=[BookLevel(price=Decimal("101"), quantity=Decimal("0")),
              BookLevel(price=Decimal("102"), quantity=Decimal("5"))],
        data_source="test", connection_id="c1",
    )


def test_contiguous_deltas_produce_complete_book():
    book = SequencedOrderBook(venue="binance", instrument="ETHUSDT")
    book.bootstrap(_snapshot())
    assert book.apply(_delta(101, 102)) is True
    assert book.apply(_delta(103, 104, previous=102)) is True
    assert book.top_of_book() == {"bid": "100", "ask": "102", "state": "COMPLETE"}
    certificate = book.certificate()
    assert certificate.state == IntegrityState.COMPLETE
    assert certificate.event_count == 2
    assert certificate.resynchronization_required is False


def test_sequence_gap_fails_closed_until_new_snapshot():
    book = SequencedOrderBook(venue="binance", instrument="ETHUSDT")
    book.bootstrap(_snapshot())
    assert book.apply(_delta(105, 106)) is False
    assert book.top_of_book()["state"] == "FAILED"
    certificate = book.certificate()
    assert certificate.gap_count == 1
    assert certificate.resynchronization_required is True
    assert "sequence_gap" in certificate.reason_codes
    assert book.apply(_delta(101, 102)) is False
    book.bootstrap(_snapshot())
    assert book.apply(_delta(101, 102)) is True


def test_stale_duplicate_does_not_mutate_book():
    book = SequencedOrderBook(venue="binance", instrument="ETHUSDT")
    book.bootstrap(_snapshot())
    assert book.apply(_delta(90, 100)) is False
    assert book.certificate().duplicate_count == 1
    assert book.top_of_book() == {"bid": "99", "ask": "101", "state": "COMPLETE"}


def test_immutable_batch_is_hash_chained_and_never_overwritten(tmp_path: Path):
    destination = tmp_path / "batch-001"
    result = write_immutable_event_batch(
        destination,
        events=[_snapshot(), _delta(101, 102)],
        metadata={"venue": "binance", "instrument": "ETHUSDT"},
    )
    assert result["event_count"] == 2
    assert verify_immutable_event_batch(destination)["status"] == "PASS"
    with pytest.raises(FileExistsError):
        write_immutable_event_batch(destination, events=[], metadata={})


def test_batch_verification_detects_tampering(tmp_path: Path):
    destination = tmp_path / "batch-001"
    write_immutable_event_batch(destination, events=[_snapshot()], metadata={})
    with (destination / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"event_kind":"tampered"}\n')
    assert verify_immutable_event_batch(destination)["status"] == "FAIL"
