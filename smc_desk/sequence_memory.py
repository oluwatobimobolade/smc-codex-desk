"""EXPERIMENTAL — SHADOW MODE ONLY. Episodic narrative of price action.

This module transforms a stream of OHLCV bars into a running story of market
structure: rallies, drops, consolidations, traps, accumulation, and distribution.
It is intentionally observability-only. It does not create TradePlan objects,
fills, or live orders. It produces narrative context that higher layers (intent
detector, fusion engine, and human reviewers) can consume.

Design principles:
- Deterministic: same bars -> same episodes.
- Incremental: process one closed bar at a time; no future leakage.
- Testable: every episode classification has explicit, measurable criteria.
- Layered: can consume engine events and visual patterns as optional evidence,
  but does not require them.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd


class EpisodeType(str, Enum):
    RALLY = "rally"
    DROP = "drop"
    CONSOLIDATION = "consolidation"
    TRAP = "trap"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    UNDEFINED = "undefined"


class EpisodeEventType(str, Enum):
    DISPLACEMENT = "displacement"
    SWEEP = "sweep"
    REVERSAL = "reversal"
    OPPOSITE_DISPLACEMENT = "opposite_displacement"
    RETRACE_50 = "retrace_50"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class EpisodeEvent:
    event_type: EpisodeEventType
    bar_index: int
    timestamp: str
    price: float
    direction: str  # bullish, bearish, neutral
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BarSnapshot:
    index: int
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def direction(self) -> str:
        return "bullish" if self.close >= self.open else "bearish"

    @property
    def upper_wick(self) -> float:
        body_top = max(self.open, self.close)
        return self.high - body_top

    @property
    def lower_wick(self) -> float:
        body_bottom = min(self.open, self.close)
        return body_bottom - self.low

    @classmethod
    def from_series(cls, index: int, row: pd.Series) -> "BarSnapshot":
        ts = row["timestamp"]
        if isinstance(ts, pd.Timestamp):
            ts = ts.isoformat()
        return cls(
            index=index,
            timestamp=str(ts),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
        )


@dataclass
class MarketEpisode:
    """A coherent period of price action with a beginning, middle, and end."""

    episode_id: str
    episode_type: EpisodeType
    start_bar: int
    start_price: float
    start_structure: str = "neutral"
    confidence: float = 1.0
    key_events: list[EpisodeEvent] = field(default_factory=list)
    parent_episode: Optional[str] = None
    child_episodes: list[str] = field(default_factory=list)

    # Mutable state while active
    end_bar: Optional[int] = None
    end_price: Optional[float] = None
    high_price: float = 0.0
    low_price: float = 0.0
    is_active: bool = True

    def __post_init__(self) -> None:
        if self.high_price == 0.0 and self.low_price == 0.0:
            self.high_price = self.start_price
            self.low_price = self.start_price

    @property
    def duration_bars(self) -> int:
        end = self.end_bar if self.end_bar is not None else self.start_bar
        return max(0, end - self.start_bar)

    @property
    def range_pct(self) -> float:
        if self.start_price == 0:
            return 0.0
        return (self.high_price - self.low_price) / abs(self.start_price)

    def update_bar(self, bar: BarSnapshot) -> None:
        self.high_price = max(self.high_price, bar.high)
        self.low_price = min(self.low_price, bar.low)

    def terminate(self, bar_index: int, end_price: float, reason: EpisodeEvent) -> None:
        self.end_bar = bar_index
        self.end_price = end_price
        self.is_active = False
        self.key_events.append(reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "episode_type": self.episode_type.value,
            "start_bar": self.start_bar,
            "end_bar": self.end_bar,
            "duration_bars": self.duration_bars,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "range_pct": round(self.range_pct, 6),
            "start_structure": self.start_structure,
            "confidence": self.confidence,
            "is_active": self.is_active,
            "key_events": [
                {
                    "event_type": e.event_type.value,
                    "bar_index": e.bar_index,
                    "timestamp": e.timestamp,
                    "price": e.price,
                    "direction": e.direction,
                    "metadata": e.metadata,
                }
                for e in self.key_events
            ],
            "parent_episode": self.parent_episode,
            "child_episodes": self.child_episodes,
        }


@dataclass
class SequenceMemoryConfig:
    """Tunable thresholds for episode detection.

    All distances are normalized in ATR or percent where practical, so the same
    config can be used across instruments without per-market fitting.
    """

    min_episode_bars: int = 3
    displacement_threshold_atr: float = 1.5
    consolidation_threshold_atr: float = 0.5
    trap_initial_bars: int = 3
    trap_reversal_bars: int = 3
    trap_min_retrace_ratio: float = 0.4
    retrace_termination_pct: float = 0.5
    opposite_displacement_threshold_atr: float = 1.0
    episode_timeout_bars: int = 48
    accumulation_max_range_pct: float = 0.005
    accumulation_min_touches: int = 3


class SequenceMemory:
    """Running episodic memory of price action.

    Process bars in chronological order. After each bar, the active episode is
    updated or terminated and a new episode is started. The result is a
    human-readable narrative plus structured episode objects for downstream use.
    """

    def __init__(self, config: Optional[SequenceMemoryConfig] = None, max_episodes: int = 50):
        self.config = config or SequenceMemoryConfig()
        self.episodes: deque[MarketEpisode] = deque(maxlen=max_episodes)
        self.active_episode: Optional[MarketEpisode] = None
        self._bar_history: list[BarSnapshot] = []
        self._episode_counter = 0

    def reset(self) -> None:
        self.episodes.clear()
        self.active_episode = None
        self._bar_history.clear()
        self._episode_counter = 0

    @property
    def bars(self) -> list[BarSnapshot]:
        return self._bar_history

    def process_dataframe(self, df: pd.DataFrame) -> "SequenceMemory":
        """Process an entire OHLCV dataframe in chronological order."""
        self.reset()
        for idx, (_, row) in enumerate(df.iterrows()):
            bar = BarSnapshot.from_series(idx, row)
            self.process_bar(bar)
        return self

    def process_bar(self, bar: BarSnapshot) -> tuple[Optional[MarketEpisode], list[MarketEpisode]]:
        """Process one closed bar and return (new_active, terminated_episodes)."""
        self._bar_history.append(bar)
        terminated: list[MarketEpisode] = []

        if self.active_episode is None:
            self._start_new_episode(bar)
            return self.active_episode, terminated

        self.active_episode.update_bar(bar)

        # Reclassify active episode as more bars become available
        if self.active_episode.episode_type == EpisodeType.UNDEFINED or self.active_episode.duration_bars >= self.config.min_episode_bars:
            episode_bars = self._bar_history[self.active_episode.start_bar : bar.index + 1]
            new_type = self._classify_bars(episode_bars)
            if new_type != EpisodeType.UNDEFINED:
                self.active_episode.episode_type = new_type

        # Detect any significant event inside the active episode
        event = self._detect_event(bar)
        if event is not None:
            self.active_episode.key_events.append(event)

        if self._should_terminate_episode(bar):
            reason = self._termination_reason(bar)
            terminated_episode = self.active_episode
            terminated_episode.terminate(bar.index, bar.close, reason)
            terminated.append(terminated_episode)
            self.episodes.append(terminated_episode)
            self._start_new_episode(bar)

        return self.active_episode, terminated

    def _start_new_episode(self, bar: BarSnapshot) -> MarketEpisode:
        self._episode_counter += 1
        episode_type = self._classify_initial_episode(bar)
        episode = MarketEpisode(
            episode_id=f"ep_{self._episode_counter:04d}",
            episode_type=episode_type,
            start_bar=bar.index,
            start_price=bar.open,
            high_price=bar.high,
            low_price=bar.low,
            is_active=True,
        )
        self.active_episode = episode
        return episode

    def _classify_initial_episode(self, bar: BarSnapshot) -> EpisodeType:
        """Classify the first bar of a new episode.

        A single bar cannot reliably be classified, so default to undefined
        unless it is a very large displacement candle.
        """
        return self._classify_bars([bar])

    def _classify_bars(self, bars: list[BarSnapshot]) -> EpisodeType:
        """Classify a sequence of bars into an episode type."""
        if len(bars) < self.config.min_episode_bars:
            if len(bars) == 1:
                atr = self._atr(bars[-1].index, lookback=14)
                if bars[0].range >= self.config.displacement_threshold_atr * atr:
                    return EpisodeType.RALLY if bars[0].close > bars[0].open else EpisodeType.DROP
                if bars[0].range <= self.config.consolidation_threshold_atr * atr:
                    return EpisodeType.CONSOLIDATION
            return EpisodeType.UNDEFINED

        start = bars[0].open
        end = bars[-1].close
        high = max(b.high for b in bars)
        low = min(b.low for b in bars)
        total_range = high - low
        atr = self._atr(bars[-1].index, 14)
        if atr <= 0:
            return EpisodeType.UNDEFINED

        # Directional consistency
        bullish_bodies = sum(1 for b in bars if b.close > b.open)
        bearish_bodies = sum(1 for b in bars if b.close < b.open)
        total = len(bars)
        consistency = max(bullish_bodies, bearish_bodies) / total

        # Rally: sustained up move
        if end > start and consistency >= 0.6 and total_range >= self.config.displacement_threshold_atr * atr:
            return EpisodeType.RALLY

        # Drop: sustained down move
        if end < start and consistency >= 0.6 and total_range >= self.config.displacement_threshold_atr * atr:
            return EpisodeType.DROP

        # Consolidation: tight range
        range_pct = total_range / max(abs(start), 1e-9)
        if range_pct < self.config.accumulation_max_range_pct * 2:
            return EpisodeType.CONSOLIDATION

        # Trap: strong initial move, immediate reversal
        if self._bars_look_like_trap(bars):
            return EpisodeType.TRAP

        return EpisodeType.UNDEFINED

    def _should_terminate_episode(self, bar: BarSnapshot) -> bool:
        if self.active_episode is None:
            return False

        episode = self.active_episode
        bars = self._bar_history
        cfg = self.config

        # Need minimum bars before considering termination
        if bar.index - episode.start_bar < cfg.min_episode_bars:
            return False

        # RULE 1: 50% retrace terminates a directional episode
        if episode.episode_type in (EpisodeType.RALLY, EpisodeType.DROP):
            if self._retrace_ratio(episode, bar.close) > cfg.retrace_termination_pct:
                return True

        # RULE 2: Trap pattern — strong initial move then immediate reversal.
        # Reclassify the episode to TRAP so it is stored and visible to intent rules.
        if self._is_trap_now(bar):
            self.active_episode.episode_type = EpisodeType.TRAP
            return True

        # RULE 3: Opposite displacement terminates any episode
        opposite_atr = cfg.opposite_displacement_threshold_atr * self._atr(bar.index, 14)
        recent_bars = bars[-cfg.min_episode_bars:]
        if recent_bars:
            recent_range = max(b.high for b in recent_bars) - min(b.low for b in recent_bars)
            if recent_range >= opposite_atr:
                if episode.episode_type == EpisodeType.RALLY and bar.close < recent_bars[0].open:
                    return True
                if episode.episode_type == EpisodeType.DROP and bar.close > recent_bars[0].open:
                    return True

        # RULE 4: Timeout — episode too long without meaningful range
        if bar.index - episode.start_bar > cfg.episode_timeout_bars:
            if episode.range_pct < cfg.accumulation_max_range_pct * 2:
                return True

        return False

    def _termination_reason(self, bar: BarSnapshot) -> EpisodeEvent:
        episode = self.active_episode
        assert episode is not None

        if self._is_trap_now(bar):
            # Trap direction from price action: if the episode made a higher high
            # than its start and is now reversing, the reversal is bearish (bull trap).
            if episode.high_price > episode.start_price:
                direction = "bearish"
            elif episode.low_price < episode.start_price:
                direction = "bullish"
            else:
                direction = "bearish" if episode.episode_type == EpisodeType.RALLY else "bullish"
            return EpisodeEvent(
                event_type=EpisodeEventType.REVERSAL,
                bar_index=bar.index,
                timestamp=bar.timestamp,
                price=bar.close,
                direction=direction,
                metadata={"reason": "trap_pattern_detected", "episode_type": episode.episode_type.value},
            )

        if episode.episode_type in (EpisodeType.RALLY, EpisodeType.DROP):
            retrace = self._retrace_ratio(episode, bar.close)
            if retrace > self.config.retrace_termination_pct:
                return EpisodeEvent(
                    event_type=EpisodeEventType.RETRACE_50,
                    bar_index=bar.index,
                    timestamp=bar.timestamp,
                    price=bar.close,
                    direction="bearish" if episode.episode_type == EpisodeType.RALLY else "bullish",
                    metadata={"retrace_ratio": round(retrace, 4)},
                )

        # Default: opposite displacement
        return EpisodeEvent(
            event_type=EpisodeEventType.OPPOSITE_DISPLACEMENT,
            bar_index=bar.index,
            timestamp=bar.timestamp,
            price=bar.close,
            direction="bearish" if episode.episode_type in (EpisodeType.RALLY, EpisodeType.ACCUMULATION) else "bullish",
            metadata={"episode_type": episode.episode_type.value},
        )

    def _detect_event(self, bar: BarSnapshot) -> Optional[EpisodeEvent]:
        """Detect a significant event within the active episode on this bar."""
        episode = self.active_episode
        if episode is None:
            return None

        atr = self._atr(bar.index, 14)
        if atr <= 0:
            return None

        # Displacement event inside a trend episode
        if episode.episode_type in (EpisodeType.RALLY, EpisodeType.DROP):
            if bar.range >= self.config.displacement_threshold_atr * atr:
                direction = "bullish" if bar.close > bar.open else "bearish"
                if (episode.episode_type == EpisodeType.RALLY and direction == "bullish") or (
                    episode.episode_type == EpisodeType.DROP and direction == "bearish"
                ):
                    return EpisodeEvent(
                        event_type=EpisodeEventType.DISPLACEMENT,
                        bar_index=bar.index,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        direction=direction,
                        metadata={"range_atr": round(bar.range / atr, 2)},
                    )

        return None

    def _bars_look_like_trap(self, bars: list[BarSnapshot]) -> bool:
        """Check if a completed bar sequence forms a trap pattern."""
        cfg = self.config
        if len(bars) < cfg.trap_initial_bars + cfg.trap_reversal_bars:
            return False

        atr = self._atr(bars[-1].index, 14)
        if atr <= 0:
            return False

        # Trap = strong move just before the reversal, not at episode start
        initial = bars[-(cfg.trap_initial_bars + cfg.trap_reversal_bars) : -cfg.trap_reversal_bars]
        reversal = bars[-cfg.trap_reversal_bars :]

        initial_range = max(b.high for b in initial) - min(b.low for b in initial)
        if initial_range < cfg.displacement_threshold_atr * atr:
            return False

        initial_direction = "up" if initial[-1].close > initial[0].open else "down"

        if initial_direction == "up":
            initial_top = max(b.high for b in initial)
            reversal_low = min(b.low for b in reversal)
            retrace = initial_top - reversal_low
            total = initial_top - min(b.low for b in initial)
        else:
            initial_bottom = min(b.low for b in initial)
            reversal_high = max(b.high for b in reversal)
            retrace = max(b.high for b in initial) - reversal_high
            total = max(b.high for b in initial) - initial_bottom

        if total <= 0:
            return False

        return retrace / total >= cfg.trap_min_retrace_ratio

    def _is_trap_now(self, bar: BarSnapshot) -> bool:
        """Detect a trap pattern: strong initial move followed by immediate reversal.

        Trap detection is conservative. We require:
        - At least trap_initial_bars + trap_reversal_bars bars in the episode.
        - Initial move is directional and >= displacement_threshold_atr * ATR.
        - Reversal retraces >= trap_min_retrace_ratio of the initial move.
        """
        episode = self.active_episode
        if episode is None:
            return False
        cfg = self.config
        duration = bar.index - episode.start_bar + 1
        if duration < cfg.trap_initial_bars + cfg.trap_reversal_bars:
            return False

        bars = self._bar_history[episode.start_bar : bar.index + 1]
        if len(bars) < cfg.trap_initial_bars + cfg.trap_reversal_bars:
            return False

        atr = self._atr(bar.index, 14)
        if atr <= 0:
            return False

        return self._bars_look_like_trap(bars)

    def _retrace_ratio(self, episode: MarketEpisode, price: float) -> float:
        """How much of a directional episode has been retraced."""
        if episode.episode_type == EpisodeType.RALLY:
            total = episode.high_price - episode.start_price
            if total <= 0:
                return 0.0
            retrace = episode.high_price - price
            return max(0.0, min(1.0, retrace / total))
        if episode.episode_type == EpisodeType.DROP:
            total = episode.start_price - episode.low_price
            if total <= 0:
                return 0.0
            retrace = price - episode.low_price
            return max(0.0, min(1.0, retrace / total))
        return 0.0

    def _atr(self, bar_index: int, lookback: int) -> float:
        """Average true range using processed bars only (no future leakage)."""
        start = max(0, bar_index - lookback + 1)
        bars = self._bar_history[start : bar_index + 1]
        if len(bars) < 2:
            return bars[0].range if bars else 1e-9

        tr_values: list[float] = []
        for i in range(1, len(bars)):
            prev_close = bars[i - 1].close
            tr = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - prev_close),
                abs(bars[i].low - prev_close),
            )
            tr_values.append(tr)
        return max(float(np.mean(tr_values)), 1e-9)

    def get_current_narrative(self, episodes_to_show: int = 3) -> str:
        """Human-readable story of recent episodes."""
        lines: list[str] = []
        recent = list(self.episodes)[-episodes_to_show:]
        for ep in recent:
            duration_hours = ep.duration_bars * 0.25  # 15m bars
            event_summary = " -> ".join(
                f"{e.event_type.value} at {e.price:.0f}" for e in ep.key_events
            ) or "no key events"
            lines.append(
                f"{ep.episode_type.value.upper()}: {ep.start_price:.0f} -> "
                f"{ep.high_price:.0f}/{ep.low_price:.0f} -> "
                f"{ep.end_price or 'active'} "
                f"({duration_hours:.1f}h) | {event_summary}"
            )

        if self.active_episode:
            active = self.active_episode
            lines.append(
                f"\nACTIVE: {active.episode_type.value} (bar {active.start_bar}+)"
            )

        lines.append(f"\nINFERENCE: {self._infer_narrative()}")
        return "\n".join(lines)

    def _infer_narrative(self) -> str:
        """High-level story: what is the market trying to do?"""
        recent = list(self.episodes)[-3:]

        # Pattern: Rally -> Trap -> Drop = Distribution complete
        if (
            len(recent) >= 3
            and recent[0].episode_type == EpisodeType.RALLY
            and recent[1].episode_type == EpisodeType.TRAP
            and recent[2].episode_type == EpisodeType.DROP
        ):
            return (
                "Distribution pattern complete. "
                "Smart money sold into the rally. "
                "Expect continuation lower or accumulation."
            )

        # Pattern: Trap episode (which started from a rally base) followed by Drop
        if (
            len(recent) >= 2
            and recent[-2].episode_type == EpisodeType.TRAP
            and recent[-2].high_price > recent[-2].start_price
            and recent[-1].episode_type == EpisodeType.DROP
        ):
            return (
                "Distribution pattern complete. "
                "Smart money sold into the rally. "
                "Expect continuation lower or accumulation."
            )

        # Pattern: Active drop after a completed bull-trap episode
        if (
            recent
            and recent[-1].episode_type == EpisodeType.TRAP
            and recent[-1].high_price > recent[-1].start_price
            and self.active_episode
            and self.active_episode.episode_type == EpisodeType.DROP
        ):
            return (
                "Distribution pattern complete. "
                "Smart money sold into the rally. "
                "Expect continuation lower or accumulation."
            )

        # Pattern: Drop -> Consolidation = Possible accumulation
        if (
            len(recent) >= 2
            and recent[-2].episode_type == EpisodeType.DROP
            and recent[-1].episode_type == EpisodeType.CONSOLIDATION
        ):
            return (
                "Selling exhausted. Watch for accumulation "
                "or continuation breakdown."
            )

        # Pattern: Trap active = Immediate danger
        if self.active_episode and self.active_episode.episode_type == EpisodeType.TRAP:
            return "TRAP IN PROGRESS. Do not chase. Wait for episode resolution."

        return "No clear narrative. Await development."

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire memory state."""
        return {
            "episodes": [ep.to_dict() for ep in self.episodes],
            "active_episode": self.active_episode.to_dict() if self.active_episode else None,
            "bar_count": len(self._bar_history),
            "episode_count": len(self.episodes) + (1 if self.active_episode else 0),
            "narrative": self.get_current_narrative(),
        }
