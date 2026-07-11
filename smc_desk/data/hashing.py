"""Deterministic hashing helpers for canonical research artefacts.

This module is intentionally dependency-light and has no imports from the
legacy engine, strategy rules, or case-library workflow.  Canonical runtime
modules may safely import it without pulling comparison authority into the
active process.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_sha256(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible research data with stable ordering."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    )


def object_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def dataframe_sha256(
    frame: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
) -> str:
    """Hash dataframe values without depending on CSV writer defaults.

    Timestamps are normalized to UTC ISO-8601 and numerics use a deterministic
    text representation.  Column order is explicit, while row order remains
    meaningful so an out-of-order source cannot hash as if it were valid.
    """
    selected = list(columns or frame.columns)
    missing = [column for column in selected if column not in frame.columns]
    if missing:
        raise ValueError(f"Cannot hash dataframe; missing columns: {missing}")

    digest = hashlib.sha256()
    digest.update(canonical_json(selected).encode("utf-8"))
    digest.update(b"\n")
    for row in frame[selected].itertuples(index=False, name=None):
        encoded = [_canonical_scalar(value) for value in row]
        digest.update(canonical_json(encoded).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_tree_manifest(
    root: str | Path,
    paths: Iterable[str | Path],
) -> dict[str, Any]:
    """Build a deterministic manifest for the exact source files in a run."""
    root_path = Path(root).resolve()
    records: list[dict[str, Any]] = []
    resolved: set[Path] = set()
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root_path / candidate
        if candidate.is_dir():
            resolved.update(path for path in candidate.rglob("*") if path.is_file())
        elif candidate.is_file():
            resolved.add(candidate)

    for path in sorted(resolved):
        relative = path.resolve().relative_to(root_path).as_posix()
        records.append(
            {
                "path": relative,
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "schema": "source_tree_manifest_v1",
        "root": root_path.name,
        "files": records,
        "manifest_sha256": object_sha256(records),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return _canonical_timestamp(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported canonical JSON type: {type(value).__name__}")


def _canonical_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return _canonical_timestamp(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numeric value cannot be hashed canonically.")
        return format(value, ".17g")
    if hasattr(value, "item"):
        return _canonical_scalar(value.item())
    return str(value)


def _canonical_timestamp(value: Any) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")
