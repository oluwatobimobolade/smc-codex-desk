"""EXPERIMENTAL — SHADOW MODE ONLY. Infer market intent from episodes and visual patterns.

The Intent Detector answers "what is the market trying to do?" by scoring
competing hypotheses against structured evidence. It is not a prediction engine;
it produces probabilistic intent classifications that downstream layers can use
to contextualize or challenge the deterministic engine.

Design principles:
- Hypotheses are explicit and falsifiable.
- Rules are modular; new intent hypotheses can be added without rewriting core.
- Scores are normalized probabilities, not arbitrary confidences.
- Observability-only by default: intent informs, it does not originate prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Protocol

from .sequence_memory import EpisodeEventType, EpisodeType, MarketEpisode, SequenceMemory


class MarketIntent(str, Enum):
    """What is the market trying to do?"""

    GENUINE_BULLISH_TREND = "genuine_bullish_trend"
    GENUINE_BEARISH_TREND = "genuine_bearish_trend"
    BULL_TRAP = "bull_trap"
    BEAR_TRAP = "bear_trap"
    BULLISH_EXHAUSTION = "bullish_exhaustion"
    BEARISH_EXHAUSTION = "bearish_exhaustion"
    SMART_MONEY_ACCUMULATING = "smart_money_accumulating"
    SMART_MONEY_DISTRIBUTING = "smart_money_distributing"
    CHOP = "chop"
    NEWS_EVENT_DISTORTION = "news_event_distortion"
    UNKNOWN = "unknown"


@dataclass
class MarketContext:
    """External context that may affect intent interpretation."""

    symbol: str = ""
    timeframe: str = "15m"
    minutes_to_next_major_news: Optional[float] = None
    is_options_expiry_day: bool = False
    options_max_pain_price: Optional[float] = None
    session: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "minutes_to_next_major_news": self.minutes_to_next_major_news,
            "is_options_expiry_day": self.is_options_expiry_day,
            "options_max_pain_price": self.options_max_pain_price,
            "session": self.session,
        }


@dataclass
class IntentMatch:
    """Result of a single intent rule evaluation."""

    intent: MarketIntent
    confidence: float  # 0.0 to 1.0
    weight: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": round(self.confidence, 4),
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass
class IntentResult:
    """Full intent classification result."""

    primary_intent: MarketIntent
    confidence: float
    all_scores: dict[MarketIntent, float] = field(default_factory=dict)
    matches: list[IntentMatch] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_intent": self.primary_intent.value,
            "confidence": round(self.confidence, 4),
            "all_scores": {k.value: round(v, 4) for k, v in self.all_scores.items()},
            "matches": [m.to_dict() for m in self.matches],
            "reasoning": self.reasoning,
        }


class IntentRule(Protocol):
    """Plugin interface for intent rules."""

    name: str
    description: str

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        ...


class SweepReversalTrapRule:
    """Price sweeps major liquidity level and immediately reverses."""

    name = "sweep_reversal_trap"
    description = (
        "Price sweeps major liquidity level and immediately reverses. "
        "Classic stop hunt pattern."
    )

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        # Active trap is handled by ActiveTrapRule to avoid double-counting.
        if active_episode and active_episode.episode_type == EpisodeType.TRAP:
            return None
        if not episodes:
            return None

        # Look for a trap episode, or a rally/drop terminated by reversal event.
        # If the trap is followed by a drop/rally continuation, let the distribution
        # rule capture the larger pattern instead.
        recent = list(episodes)[-3:]
        for i, ep in enumerate(recent):
            if ep.episode_type == EpisodeType.TRAP:
                # If trap is followed by continuation, this is distribution/accumulation
                if i + 1 < len(recent):
                    next_ep = recent[i + 1]
                    if next_ep.episode_type == EpisodeType.DROP:
                        continue
                    if next_ep.episode_type == EpisodeType.RALLY:
                        continue
                direction = "bearish"
                for ev in ep.key_events:
                    if ev.event_type == EpisodeEventType.REVERSAL:
                        direction = ev.direction
                intent = (
                    MarketIntent.BULL_TRAP
                    if direction == "bearish"
                    else MarketIntent.BEAR_TRAP
                )
                return IntentMatch(
                    intent=intent,
                    confidence=0.85,
                    weight=1.0,
                    reason=f"Trap episode detected with {direction} reversal.",
                )

        # Or a directional episode terminated by a reversal event
        if recent:
            last = recent[-1]
            for ev in last.key_events:
                if ev.event_type == EpisodeEventType.REVERSAL:
                    intent = (
                        MarketIntent.BULL_TRAP
                        if ev.direction == "bearish"
                        else MarketIntent.BEAR_TRAP
                    )
                    return IntentMatch(
                        intent=intent,
                        confidence=0.75,
                        weight=0.9,
                        reason="Directional episode terminated by reversal event.",
                    )

        return None


class VerticalSpikeTrapRule:
    """Rally accelerates vertically, wicks above resistance, collapses immediately."""

    name = "vertical_spike_bull_trap"
    description = (
        "Rally accelerates vertically, wicks above resistance, "
        "collapses immediately. FOMO trap."
    )

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        for pattern in visual_patterns:
            if pattern.get("pattern_type") == "vertical_spike_trap":
                direction = pattern.get("direction", "neutral")
                intent = (
                    MarketIntent.BULL_TRAP
                    if direction == "bearish"
                    else MarketIntent.BEAR_TRAP
                )
                confidence = pattern.get("confidence", 0.7)
                return IntentMatch(
                    intent=intent,
                    confidence=min(0.95, confidence),
                    weight=1.0,
                    reason="Visual cortex detected vertical spike trap.",
                )
        return None


class RallyThenTrapDistributionRule:
    """Rally -> Trap -> Drop episode sequence indicates distribution."""

    name = "rally_trap_drop_distribution"
    description = (
        "Rally followed by trap and drop indicates smart money "
        "distributed into the rally."
    )

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        recent = list(episodes)[-3:]
        # Explicit rally -> trap -> drop
        if (
            len(recent) >= 3
            and recent[0].episode_type == EpisodeType.RALLY
            and recent[1].episode_type == EpisodeType.TRAP
            and recent[2].episode_type == EpisodeType.DROP
        ):
            return IntentMatch(
                intent=MarketIntent.SMART_MONEY_DISTRIBUTING,
                confidence=0.8,
                weight=0.9,
                reason="Rally -> Trap -> Drop episode sequence.",
            )
        # Trap episode that started from a rally base, followed by drop
        if (
            len(recent) >= 2
            and recent[-2].episode_type == EpisodeType.TRAP
            and recent[-2].high_price > recent[-2].start_price
            and recent[-1].episode_type == EpisodeType.DROP
        ):
            return IntentMatch(
                intent=MarketIntent.SMART_MONEY_DISTRIBUTING,
                confidence=0.78,
                weight=0.85,
                reason="Bull trap episode followed by drop indicates distribution.",
            )
        # Completed bull trap with active drop continuation
        if (
            recent
            and recent[-1].episode_type == EpisodeType.TRAP
            and recent[-1].high_price > recent[-1].start_price
            and active_episode
            and active_episode.episode_type == EpisodeType.DROP
        ):
            return IntentMatch(
                intent=MarketIntent.SMART_MONEY_DISTRIBUTING,
                confidence=0.9,
                weight=1.0,
                reason="Completed bull trap with active drop continuation.",
            )
        return None


class DropThenConsolidationAccumulationRule:
    """Drop followed by tight consolidation suggests accumulation."""

    name = "drop_consolidation_accumulation"
    description = "Selling exhausted, price consolidating after drop."

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        recent = list(episodes)[-2:]
        if (
            len(recent) >= 2
            and recent[-2].episode_type == EpisodeType.DROP
            and recent[-1].episode_type == EpisodeType.CONSOLIDATION
        ):
            return IntentMatch(
                intent=MarketIntent.SMART_MONEY_ACCUMULATING,
                confidence=0.65,
                weight=0.7,
                reason="Drop followed by tight consolidation.",
            )
        return None


class MultipleFailedBreakoutsRule:
    """Multiple failed breakouts suggest exhaustion."""

    name = "multiple_failed_breakouts"
    description = "Price tests level multiple times and fails."

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        failed_breakouts = [p for p in visual_patterns if p.get("pattern_type") == "failed_breakout"]
        if len(failed_breakouts) >= 2:
            directions = {p.get("direction") for p in failed_breakouts}
            if "bearish" in directions:
                return IntentMatch(
                    intent=MarketIntent.BULLISH_EXHAUSTION,
                    confidence=0.7,
                    weight=0.8,
                    reason="Multiple bullish failed breakouts.",
                )
            if "bullish" in directions:
                return IntentMatch(
                    intent=MarketIntent.BEARISH_EXHAUSTION,
                    confidence=0.7,
                    weight=0.8,
                    reason="Multiple bearish failed breakouts.",
                )
        return None


class NewsEventDistortionRule:
    """Major economic release imminent; technicals unreliable."""

    name = "news_event_proximity"
    description = "Major news event close to decision time."

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        if (
            context.minutes_to_next_major_news is not None
            and context.minutes_to_next_major_news < 30
        ):
            return IntentMatch(
                intent=MarketIntent.NEWS_EVENT_DISTORTION,
                confidence=0.95,
                weight=1.0,
                reason="Major news event within 30 minutes.",
            )
        return None


class ActiveTrapRule:
    """Active trap episode means danger; no directional intent yet."""

    name = "active_trap"
    description = "A trap episode is currently active."

    def evaluate(
        self,
        episodes: list[MarketEpisode],
        active_episode: Optional[MarketEpisode],
        visual_patterns: list[dict[str, Any]],
        context: MarketContext,
    ) -> Optional[IntentMatch]:
        if active_episode and active_episode.episode_type == EpisodeType.TRAP:
            return IntentMatch(
                intent=MarketIntent.CHOP,
                confidence=0.7,
                weight=0.8,
                reason="Active trap episode; await resolution.",
            )
        return None


@dataclass
class IntentDetectorConfig:
    """Configuration for intent detection."""

    min_confidence_for_override: float = 0.85
    default_intent: MarketIntent = MarketIntent.UNKNOWN


class IntentDetector:
    """Top-level intent detection pipeline."""

    def __init__(self, config: Optional[IntentDetectorConfig] = None):
        self.config = config or IntentDetectorConfig()
        self.rules: list[IntentRule] = [
            NewsEventDistortionRule(),
            ActiveTrapRule(),
            VerticalSpikeTrapRule(),
            SweepReversalTrapRule(),
            RallyThenTrapDistributionRule(),
            DropThenConsolidationAccumulationRule(),
            MultipleFailedBreakoutsRule(),
        ]

    def register_rule(self, rule: IntentRule) -> None:
        self.rules.append(rule)

    def detect_intent(
        self,
        sequence_memory: SequenceMemory,
        visual_patterns: Optional[list[dict[str, Any]]] = None,
        context: Optional[MarketContext] = None,
    ) -> IntentResult:
        """Score intent hypotheses from current market state."""
        episodes = list(sequence_memory.episodes)
        active = sequence_memory.active_episode
        visual_patterns = visual_patterns or []
        context = context or MarketContext()

        matches: list[IntentMatch] = []
        for rule in self.rules:
            match = rule.evaluate(episodes, active, visual_patterns, context)
            if match is not None:
                matches.append(match)

        # Aggregate scores by intent
        scores: dict[MarketIntent, float] = {intent: 0.0 for intent in MarketIntent}
        for match in matches:
            scores[match.intent] += match.confidence * match.weight

        # Small baseline for unknown to avoid division issues
        scores[MarketIntent.UNKNOWN] += 0.01

        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        primary_intent = max(scores, key=scores.get)
        confidence = scores[primary_intent]

        reasoning = self._generate_reasoning(primary_intent, matches, active)

        return IntentResult(
            primary_intent=primary_intent,
            confidence=confidence,
            all_scores=scores,
            matches=matches,
            reasoning=reasoning,
        )

    def _generate_reasoning(
        self,
        primary_intent: MarketIntent,
        matches: list[IntentMatch],
        active: Optional[MarketEpisode],
    ) -> str:
        reasons = [m.reason for m in matches if m.intent == primary_intent]
        if not reasons:
            reasons = [m.reason for m in matches[:1]]
        base = " ".join(reasons) if reasons else "No strong intent signals."
        if active:
            base += f" Active episode: {active.episode_type.value}."
        return base
