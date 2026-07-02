"""Market truth validation for the colleague cognitive pipeline.

This layer is deliberately stricter than ordinary data quality reporting.
If market truth fails, downstream perception must not run. A chart reader can
be uncertain, but it must not reason from incomplete or contradictory OHLCV.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from smc_desk.data.schemas import Candle


TIMEFRAME_STEPS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True)
class TruthIssue:
    code: str
    severity: str
    message: str
    provider: str = "primary"
    timeframe: str = ""
    candle_open_time: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "provider": self.provider,
            "timeframe": self.timeframe,
            "candle_open_time": self.candle_open_time,
            "message": self.message,
        }


@dataclass(frozen=True)
class TimeframeTruthSummary:
    provider: str
    timeframe: str
    candle_count: int
    first_open_time: str | None
    last_close_time: str | None
    status: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "timeframe": self.timeframe,
            "candle_count": self.candle_count,
            "first_open_time": self.first_open_time,
            "last_close_time": self.last_close_time,
            "status": self.status,
        }


@dataclass(frozen=True)
class MarketTruthReport:
    status: str
    decision_time: datetime
    provider_count: int
    timeframe_summaries: list[TimeframeTruthSummary] = field(default_factory=list)
    issues: list[TruthIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "PASS"

    @property
    def refuse_perception(self) -> bool:
        return not self.ok

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "decision_time": self.decision_time.isoformat(),
            "provider_count": self.provider_count,
            "refuse_perception": self.refuse_perception,
            "timeframe_summaries": [summary.to_dict() for summary in self.timeframe_summaries],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validate_market_truth(
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    decision_time: datetime,
    *,
    expected_instrument: str | None = None,
    expected_timeframes: Iterable[str] | None = None,
    provider_feeds: Mapping[str, Mapping[str, Sequence[Candle]]] | None = None,
    provider_price_tolerance_bps: float = 1.0,
    provider_overlap_bars: int = 20,
) -> MarketTruthReport:
    """Validate OHLCV truth before perception.

    Args:
        candles_by_timeframe: Primary feed candles, keyed by timeframe.
        decision_time: The as-of time. All candles must be closed by this time.
        expected_instrument: Optional instrument guard.
        expected_timeframes: Timeframes that must exist and be non-empty.
        provider_feeds: Optional multiple-provider feeds, keyed by provider name.
        provider_price_tolerance_bps: OHLC tolerance for feed reconciliation.
        provider_overlap_bars: Number of most recent overlapping bars to compare.
    """
    _require_aware(decision_time)
    feeds = provider_feeds or {"primary": candles_by_timeframe}
    expected = list(expected_timeframes or candles_by_timeframe.keys())
    issues: list[TruthIssue] = []
    summaries: list[TimeframeTruthSummary] = []

    for provider, feed in feeds.items():
        for timeframe in expected:
            candles = list(feed.get(timeframe, ()))
            tf_issues = _validate_single_feed(
                candles,
                decision_time,
                provider=provider,
                timeframe=timeframe,
                expected_instrument=expected_instrument,
            )
            issues.extend(tf_issues)
            summaries.append(_summarize(provider, timeframe, candles, tf_issues))

    if len(feeds) > 1:
        issues.extend(
            _validate_provider_consistency(
                feeds,
                expected,
                tolerance_bps=provider_price_tolerance_bps,
                overlap_bars=provider_overlap_bars,
            )
        )

    return MarketTruthReport(
        status="REFUSE_PERCEPTION" if issues else "PASS",
        decision_time=decision_time,
        provider_count=len(feeds),
        timeframe_summaries=summaries,
        issues=issues,
    )


def _validate_single_feed(
    candles: Sequence[Candle],
    decision_time: datetime,
    *,
    provider: str,
    timeframe: str,
    expected_instrument: str | None,
) -> list[TruthIssue]:
    issues: list[TruthIssue] = []
    if not candles:
        return [
            TruthIssue(
                code="missing_timeframe_data",
                severity="critical",
                provider=provider,
                timeframe=timeframe,
                message=f"No candles supplied for {timeframe}.",
            )
        ]

    step = TIMEFRAME_STEPS.get(timeframe)
    previous: Candle | None = None
    seen_opens: set[datetime] = set()
    for candle in candles:
        _require_aware(candle.open_time)
        _require_aware(candle.close_time)
        candle_time = candle.open_time.isoformat()

        if expected_instrument and candle.instrument != expected_instrument:
            issues.append(
                TruthIssue(
                    code="instrument_mismatch",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message=f"Expected {expected_instrument}, got {candle.instrument}.",
                )
            )
        if candle.timeframe != timeframe:
            issues.append(
                TruthIssue(
                    code="timeframe_mismatch",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message=f"Expected timeframe {timeframe}, got {candle.timeframe}.",
                )
            )
        if candle.open_time in seen_opens:
            issues.append(
                TruthIssue(
                    code="duplicate_timestamp",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Duplicate candle open timestamp.",
                )
            )
        seen_opens.add(candle.open_time)

        if candle.close_time <= candle.open_time:
            issues.append(
                TruthIssue(
                    code="invalid_candle_time_range",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Candle close time must be after open time.",
                )
            )
        if step and candle.close_time - candle.open_time != step:
            issues.append(
                TruthIssue(
                    code="unexpected_candle_duration",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message=f"Expected {step}, got {candle.close_time - candle.open_time}.",
                )
            )
        if candle.close_time > decision_time:
            issues.append(
                TruthIssue(
                    code="unfinalized_candle",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Candle closes after the decision time.",
                )
            )
        if not candle.is_closed:
            issues.append(
                TruthIssue(
                    code="candle_not_closed",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Candle is marked not closed.",
                )
            )
        if not candle.is_complete:
            issues.append(
                TruthIssue(
                    code="candle_not_complete",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Candle is marked incomplete.",
                )
            )
        if candle.contains_gap:
            issues.append(
                TruthIssue(
                    code="candle_contains_gap",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="Candle is marked as containing a gap.",
                )
            )
        if not _valid_ohlcv(candle):
            issues.append(
                TruthIssue(
                    code="invalid_ohlcv",
                    severity="critical",
                    provider=provider,
                    timeframe=timeframe,
                    candle_open_time=candle_time,
                    message="OHLCV values violate high/low bounds or non-negative volume.",
                )
            )

        if previous is not None:
            if candle.open_time <= previous.open_time:
                issues.append(
                    TruthIssue(
                        code="non_monotonic_timestamp",
                        severity="critical",
                        provider=provider,
                        timeframe=timeframe,
                        candle_open_time=candle_time,
                        message="Candle open times must be strictly increasing.",
                    )
                )
            if step and candle.open_time - previous.open_time != step:
                issues.append(
                    TruthIssue(
                        code="missing_data_gap",
                        severity="critical",
                        provider=provider,
                        timeframe=timeframe,
                        candle_open_time=candle_time,
                        message=f"Expected next open {previous.open_time + step}, got {candle.open_time}.",
                    )
                )
            if candle.open_time != previous.close_time:
                issues.append(
                    TruthIssue(
                        code="open_close_continuity_gap",
                        severity="critical",
                        provider=provider,
                        timeframe=timeframe,
                        candle_open_time=candle_time,
                        message=f"Previous candle closed at {previous.close_time}, current opened at {candle.open_time}.",
                    )
                )
        previous = candle

    return issues


def _validate_provider_consistency(
    feeds: Mapping[str, Mapping[str, Sequence[Candle]]],
    timeframes: Sequence[str],
    *,
    tolerance_bps: float,
    overlap_bars: int,
) -> list[TruthIssue]:
    issues: list[TruthIssue] = []
    providers = list(feeds.keys())
    primary = providers[0]
    for provider in providers[1:]:
        for timeframe in timeframes:
            primary_by_time = {c.open_time: c for c in feeds[primary].get(timeframe, ())}
            other_by_time = {c.open_time: c for c in feeds[provider].get(timeframe, ())}
            overlap = sorted(set(primary_by_time) & set(other_by_time))[-overlap_bars:]
            if not overlap:
                issues.append(
                    TruthIssue(
                        code="provider_overlap_missing",
                        severity="critical",
                        provider=provider,
                        timeframe=timeframe,
                        message=f"No overlapping candles with provider {primary}.",
                    )
                )
                continue
            for open_time in overlap:
                a = primary_by_time[open_time]
                b = other_by_time[open_time]
                for field in ("open", "high", "low", "close"):
                    if _bps_difference(getattr(a, field), getattr(b, field)) > tolerance_bps:
                        issues.append(
                            TruthIssue(
                                code="provider_ohlc_mismatch",
                                severity="critical",
                                provider=provider,
                                timeframe=timeframe,
                                candle_open_time=open_time.isoformat(),
                                message=(
                                    f"{field} differs from provider {primary} by more than "
                                    f"{tolerance_bps} bps."
                                ),
                            )
                        )
                        break
    return issues


def _valid_ohlcv(candle: Candle) -> bool:
    if candle.high < candle.low:
        return False
    if not (candle.low <= candle.open <= candle.high):
        return False
    if not (candle.low <= candle.close <= candle.high):
        return False
    return candle.volume >= 0


def _bps_difference(a: Decimal, b: Decimal) -> float:
    base = (abs(a) + abs(b)) / Decimal("2")
    if base == 0:
        return 0.0 if a == b else float("inf")
    return float(abs(a - b) / base * Decimal("10000"))


def _summarize(
    provider: str,
    timeframe: str,
    candles: Sequence[Candle],
    issues: Sequence[TruthIssue],
) -> TimeframeTruthSummary:
    tf_issues = [issue for issue in issues if issue.provider == provider and issue.timeframe == timeframe]
    return TimeframeTruthSummary(
        provider=provider,
        timeframe=timeframe,
        candle_count=len(candles),
        first_open_time=None if not candles else candles[0].open_time.isoformat(),
        last_close_time=None if not candles else candles[-1].close_time.isoformat(),
        status="PASS" if not tf_issues else "FAIL",
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("Market truth validation requires timezone-aware datetimes.")
