"""Episode Narrative Builder — market-phase layer over engine structure events.

This module replaces the independent bar-based episode classification in
sequence_memory.py with a layer that derives episodes from the same
engine-recognized structure the state machine already uses: liquidity sweeps,
BOS/CHoCH displacement, and invalidations.

Design principles:
- Single source of truth for temporal structure: the deterministic engine.
- Descriptive only: episodes label what has happened, they do not decide trades.
- No future leakage: classification uses events available at the current bar.
- Backward-compatible output: produces the same MarketEpisode / EpisodeEvent types
  that intent_detector.py and fusion_engine.py already consume.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import StructureEvent
from .sequence_memory import (
    BarSnapshot,
    EpisodeEvent,
    EpisodeEventType,
    EpisodeType,
    MarketEpisode,
)


@dataclass
class EpisodeNarrativeBuilder:
    """Build MarketEpisode objects from engine StructureEvents.

    The builder processes one closed bar at a time. It uses sweep/displacement
    events to decide when a new episode starts and what type it is. Raw bar
    data is used only to track episode high/low and to detect consolidation
    timeouts.
    """

    consolidation_timeout_bars: int = 8
    episodes: deque[MarketEpisode] = field(default_factory=lambda: deque(maxlen=100))
    active_episode: MarketEpisode | None = None
    _last_event_bar: int = -1
    _pending_sweep: EpisodeEvent | None = None

    def reset(self) -> None:
        self.episodes.clear()
        self.active_episode = None
        self._last_event_bar = -1
        self._pending_sweep = None

    def process_bar(
        self,
        bar: BarSnapshot,
        structure_events: list[StructureEvent],
    ) -> None:
        """Process one closed bar and its engine-recognized structure events."""
        sweeps = [e for e in structure_events if e.label == "Liquidity Sweep"]
        breaks = [e for e in structure_events if e.label in {"BOS", "CHoCH"}]

        # Update active episode high/low from bar data.
        if self.active_episode is not None:
            self.active_episode.high_price = max(
                getattr(self.active_episode, "high_price", bar.low), bar.high
            )
            self.active_episode.low_price = min(
                getattr(self.active_episode, "low_price", bar.high), bar.low
            )

        # Handle sweeps.
        for sweep in sweeps:
            self._handle_sweep(bar, sweep)

        # Handle displacement breaks.
        for break_event in breaks:
            self._handle_break(bar, break_event)

        # Timeout into consolidation if no events for too long.
        if self.active_episode is not None and not sweeps and not breaks:
            if bar.index - self._last_event_bar > self.consolidation_timeout_bars:
                # Only create a new consolidation if we're not already in one.
                if self.active_episode.episode_type != EpisodeType.CONSOLIDATION:
                    self._terminate_active(
                        bar.index,
                        str(bar.timestamp),
                        EpisodeEventType.TIMEOUT,
                        "no structure events; consolidate",
                    )
                    self._start_episode(
                        bar,
                        EpisodeType.CONSOLIDATION,
                        EpisodeEventType.TIMEOUT,
                        "consolidation after structure silence",
                        confidence=0.6,
                    )

        if sweeps or breaks:
            self._last_event_bar = bar.index

    def _handle_sweep(self, bar: BarSnapshot, sweep: StructureEvent) -> None:
        """A sweep starts or confirms a new episode direction."""
        event = EpisodeEvent(
            event_type=EpisodeEventType.SWEEP,
            bar_index=bar.index,
            timestamp=str(bar.timestamp),
            price=sweep.price,
            direction=sweep.direction,
            metadata={"structure_scope": getattr(sweep, "structure_scope", "unknown")},
        )

        # If current episode is opposite direction, terminate it (the sweep
        # indicates a potential reversal).
        if self.active_episode is not None:
            active_direction = self._episode_direction(self.active_episode.episode_type)
            if active_direction is not None and sweep.direction != active_direction:
                self._terminate_active(
                    bar.index,
                    str(bar.timestamp),
                    EpisodeEventType.SWEEP,
                    f"{sweep.direction} sweep interrupts {active_direction} episode",
                )

        # Store pending sweep; displacement on the same/next bars will turn it
        # into a rally/drop. Without displacement it becomes a trap.
        self._pending_sweep = event

        # Start a provisional episode.
        if self.active_episode is None:
            self._start_episode(
                bar,
                EpisodeType.CONSOLIDATION,
                EpisodeEventType.SWEEP,
                f"{sweep.direction} liquidity sweep; awaiting displacement",
                confidence=0.5,
            )

    def _handle_break(self, bar: BarSnapshot, break_event: StructureEvent) -> None:
        """A displacement break confirms direction and starts rally/drop."""
        event = EpisodeEvent(
            event_type=EpisodeEventType.DISPLACEMENT,
            bar_index=bar.index,
            timestamp=str(bar.timestamp),
            price=break_event.price,
            direction=break_event.direction,
            metadata={
                "structure_scope": getattr(break_event, "structure_scope", "unknown"),
                "strength": getattr(break_event, "strength", "valid"),
            },
        )

        direction = break_event.direction
        new_type = EpisodeType.RALLY if direction == "bullish" else EpisodeType.DROP

        # If we have a pending sweep in the same direction, this is a clean
        # sweep-then-break model.
        if (
            self._pending_sweep is not None
            and self._pending_sweep.direction == direction
        ):
            # Convert the provisional episode into a confirmed trend episode.
            if self.active_episode is not None:
                self.active_episode.episode_type = new_type
                self.active_episode.confidence = 0.85
                self.active_episode.key_events.append(self._pending_sweep)
                self.active_episode.key_events.append(event)
            else:
                self._start_episode(
                    bar,
                    new_type,
                    EpisodeEventType.DISPLACEMENT,
                    f"{direction} displacement after sweep",
                    confidence=0.85,
                    key_events=[self._pending_sweep, event],
                )
            self._pending_sweep = None
            return

        # Break without a matching pending sweep: either a continuation or a
        # reversal of the active episode.
        # If there is a pending sweep in the OPPOSITE direction, it was a
        # failed sweep (trap): terminate the active episode as a trap first.
        if (
            self._pending_sweep is not None
            and self._pending_sweep.direction != direction
            and self.active_episode is not None
        ):
            self.active_episode.episode_type = EpisodeType.TRAP
            self.active_episode.confidence = 0.75
            self.active_episode.key_events.append(self._pending_sweep)
            self._pending_sweep = None
            self._terminate_active(
                bar.index,
                str(bar.timestamp),
                EpisodeEventType.REVERSAL,
                f"pending {self.active_episode.episode_type.value} sweep failed; "
                f"{direction} displacement reverses",
            )

        if self.active_episode is not None:
            active_direction = self._episode_direction(self.active_episode.episode_type)
            if active_direction == direction:
                # Continuation.
                self.active_episode.key_events.append(event)
                return
            if active_direction is not None:
                # Reversal.
                self._terminate_active(
                    bar.index,
                    str(bar.timestamp),
                    EpisodeEventType.OPPOSITE_DISPLACEMENT,
                    f"{direction} displacement reverses {active_direction} episode",
                )

        # Fresh break with no context.
        self._start_episode(
            bar,
            new_type,
            EpisodeEventType.DISPLACEMENT,
            f"{direction} displacement",
            confidence=0.7,
            key_events=[event],
        )

    def _start_episode(
        self,
        bar: BarSnapshot,
        episode_type: EpisodeType,
        trigger_event_type: EpisodeEventType,
        reason: str,
        confidence: float = 1.0,
        key_events: list[EpisodeEvent] | None = None,
    ) -> None:
        if self.active_episode is not None:
            self._archive_active(bar.index, bar.close)

        event = EpisodeEvent(
            event_type=trigger_event_type,
            bar_index=bar.index,
            timestamp=str(bar.timestamp),
            price=bar.close,
            direction="neutral",
            metadata={"reason": reason},
        )
        events = list(key_events or [])
        events.append(event)

        self.active_episode = MarketEpisode(
            episode_id=f"ep_{bar.index:04d}",
            episode_type=episode_type,
            start_bar=bar.index,
            start_price=bar.close,
            start_structure=episode_type.value,
            confidence=confidence,
            key_events=events,
            high_price=bar.high,
            low_price=bar.low,
        )

    def _terminate_active(
        self,
        bar_index: int,
        timestamp: str,
        event_type: EpisodeEventType,
        reason: str,
    ) -> None:
        if self.active_episode is None:
            return

        # Pending sweep that never got displacement becomes a trap.
        if (
            self._pending_sweep is not None
            and self.active_episode.episode_type == EpisodeType.CONSOLIDATION
        ):
            self.active_episode.episode_type = EpisodeType.TRAP
            self.active_episode.confidence = 0.75
            self.active_episode.key_events.append(self._pending_sweep)
            self._pending_sweep = None

        event = EpisodeEvent(
            event_type=event_type,
            bar_index=bar_index,
            timestamp=timestamp,
            price=self.active_episode.end_price or self.active_episode.start_price,
            direction="neutral",
            metadata={"reason": reason},
        )
        self.active_episode.key_events.append(event)
        self._archive_active(bar_index, self.active_episode.end_price)

    def _archive_active(self, end_bar: int, end_price: float | None) -> None:
        if self.active_episode is None:
            return
        self.active_episode.end_bar = end_bar
        self.active_episode.end_price = end_price
        self.active_episode.is_active = False
        self.episodes.append(self.active_episode)
        self.active_episode = None

    @staticmethod
    def _episode_direction(episode_type: EpisodeType) -> str | None:
        mapping = {
            EpisodeType.RALLY: "bullish",
            EpisodeType.DROP: "bearish",
        }
        return mapping.get(episode_type)

    def get_current_narrative(self, episodes_to_show: int = 3) -> str:
        """Return a short human-readable narrative of recent episodes."""
        recent = list(self.episodes)[-episodes_to_show:]
        if self.active_episode is not None:
            recent = recent + [self.active_episode]

        lines: list[str] = []
        for ep in recent:
            end_price = ep.end_price if ep.end_price is not None else "?"
            end_bar = ep.end_bar if ep.end_bar is not None else "active"
            key = ", ".join(e.event_type.value for e in ep.key_events[:2])
            lines.append(
                f"{ep.episode_type.value.upper()}: "
                f"{ep.start_price:.5f} -> {end_price} "
                f"(bars {ep.start_bar}-{end_bar}) | {key}"
            )

        if self.active_episode is not None:
            lines.append(f"\nACTIVE: {self.active_episode.episode_type.value} (bar {self.active_episode.start_bar}+)")

        if not lines:
            return "No episodes yet."
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episodes": [ep.to_dict() for ep in self.episodes],
            "active_episode": self.active_episode.to_dict() if self.active_episode else None,
            "narrative": self.get_current_narrative(),
        }
