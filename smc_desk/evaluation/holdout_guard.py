"""Holdout-window guards for local research tools.

The guard is intentionally small and boring: research tools pass the symbol,
time span, and action they are about to perform, and the guard raises if that
span overlaps a locked evaluation window.  This prevents accidental tuning on
periods that are meant to stay untouched.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOLDOUT_POLICY = ROOT / "configs" / "holdout_policy.local_first.json"


class HoldoutViolation(RuntimeError):
    """Raised when a research action overlaps a locked holdout window."""


def normalize_symbol(value: str | None) -> str:
    if not value:
        return "*"
    raw = value.strip().upper().replace("/", "").replace("-", "")
    if raw.endswith("USD") and not raw.endswith("USDT"):
        return raw[:-3] + "USDT"
    return raw


def parse_timestamp(value: Any) -> pd.Timestamp:
    if value is None:
        raise ValueError("Holdout timestamps cannot be None.")
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")
    return parsed


@dataclass(frozen=True)
class HoldoutWindow:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp | None
    symbols: tuple[str, ...] = ("*",)
    actions: tuple[str, ...] = ("*",)
    reason: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HoldoutWindow":
        symbols = tuple(normalize_symbol(symbol) for symbol in payload.get("symbols", ["*"]))
        actions = tuple(str(action).strip().lower() for action in payload.get("actions", ["*"]))
        return cls(
            name=str(payload["name"]),
            start=parse_timestamp(payload["start"]),
            end=None if payload.get("end") in {None, ""} else parse_timestamp(payload["end"]),
            symbols=symbols or ("*",),
            actions=actions or ("*",),
            reason=str(payload.get("reason") or ""),
        )

    def matches(self, *, start: Any, end: Any, symbol: str | None, action: str) -> bool:
        interval_start = parse_timestamp(start)
        interval_end = parse_timestamp(end)
        if interval_end < interval_start:
            raise ValueError("Research interval end must be >= start.")

        normalized_symbol = normalize_symbol(symbol)
        normalized_action = str(action).strip().lower()
        if "*" not in self.symbols and normalized_symbol not in self.symbols:
            return False
        if "*" not in self.actions and normalized_action not in self.actions:
            return False

        window_end = self.end or pd.Timestamp.max.tz_localize("UTC")
        return interval_start <= window_end and interval_end >= self.start


@dataclass(frozen=True)
class HoldoutPolicy:
    path: Path | None
    windows: tuple[HoldoutWindow, ...]

    def overlaps(self, *, start: Any, end: Any, symbol: str | None, action: str) -> list[HoldoutWindow]:
        return [window for window in self.windows if window.matches(start=start, end=end, symbol=symbol, action=action)]


def load_holdout_policy(path: str | Path | None = None) -> HoldoutPolicy:
    policy_path = Path(path).expanduser() if path else DEFAULT_HOLDOUT_POLICY
    if not policy_path.exists():
        return HoldoutPolicy(path=policy_path, windows=())
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    windows = tuple(HoldoutWindow.from_dict(item) for item in payload.get("windows", []))
    return HoldoutPolicy(path=policy_path, windows=windows)


def assert_not_in_holdout(
    *,
    start: Any,
    end: Any,
    symbol: str | None,
    action: str,
    policy_path: str | Path | None = None,
    allow_holdout: bool = False,
) -> list[HoldoutWindow]:
    """Raise if an action overlaps a locked holdout window.

    Returns the matching windows so callers can record provenance when
    ``allow_holdout`` is deliberately enabled for a final evaluation run.
    """
    policy = load_holdout_policy(policy_path)
    matches = policy.overlaps(start=start, end=end, symbol=symbol, action=action)
    if matches and not allow_holdout:
        names = ", ".join(window.name for window in matches)
        source = f" from {policy.path}" if policy.path else ""
        raise HoldoutViolation(
            f"{action} for {normalize_symbol(symbol)} from {parse_timestamp(start).isoformat()} "
            f"to {parse_timestamp(end).isoformat()} overlaps locked holdout window(s){source}: {names}. "
            "Use an explicit allow-holdout flag only for final evaluation."
        )
    return matches
