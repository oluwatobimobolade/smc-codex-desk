"""EXPERIMENTAL — SHADOW MODE ONLY. Reconcile deterministic engine with narrative and visual layers.

The Fusion Engine scores the engine's own bullish and bearish TradePlans against
one another. It does not invent prices. It may downgrade a verdict and it may
flag a contested state, but it never upgrades a Pass into an Execute.

Safety contract (observability-only by default):
- The deterministic engine owns all prices (entry, stop, target).
- The Fusion Engine may downgrade a verdict (Execute -> Watch -> Pass).
- The Fusion Engine may flag a direction as contested.
- The Fusion Engine may NOT invent new price levels.
- The Fusion Engine may NOT upgrade a Pass/Watch into an Execute.
- Every change is recorded as an override with full reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .intent_detector import IntentResult, MarketIntent
from .models import AnalysisResult, TradePlan
from .sequence_memory import SequenceMemory


@dataclass
class FusionContribution:
    """One layer's contribution to the fused decision."""

    layer: str
    verdict: str
    bias: str
    confidence: float
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "verdict": self.verdict,
            "bias": self.bias,
            "confidence": round(self.confidence, 4),
            "notes": self.notes,
        }


@dataclass
class FusionOverride:
    """Record of a change the fusion engine made to the baseline."""

    source: str
    field: str
    old_value: str
    new_value: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class FusionResult:
    """Output of the Fusion Engine."""

    # Engine primary baseline (authoritative prices)
    engine_primary_verdict: str
    engine_primary_bias: str
    engine_primary_grade: str
    engine_primary_confidence: float

    # Dual-plan scores and selections
    bullish_plan_summary: dict[str, Any] = field(default_factory=dict)
    bearish_plan_summary: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)

    # Fused recommendation (only verdict/bias may be downgraded)
    recommended_direction: str = "neutral"
    recommended_verdict: str = "Pass"
    recommended_grade: str = "C"
    fused_confidence: float = 0.0
    contested: bool = False

    # Conflict and contribution records
    overrides: list[FusionOverride] = field(default_factory=list)
    contributions: list[FusionContribution] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    # Price provenance: every emitted price must trace to the engine
    price_sources: dict[str, str] = field(default_factory=dict)

    # Narrative context
    narrative: str = ""
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_primary_verdict": self.engine_primary_verdict,
            "engine_primary_bias": self.engine_primary_bias,
            "engine_primary_grade": self.engine_primary_grade,
            "engine_primary_confidence": round(self.engine_primary_confidence, 4),
            "bullish_plan_summary": self.bullish_plan_summary,
            "bearish_plan_summary": self.bearish_plan_summary,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "recommended_direction": self.recommended_direction,
            "recommended_verdict": self.recommended_verdict,
            "recommended_grade": self.recommended_grade,
            "fused_confidence": round(self.fused_confidence, 4),
            "contested": self.contested,
            "overrides": [o.to_dict() for o in self.overrides],
            "contributions": [c.to_dict() for c in self.contributions],
            "conflicts": self.conflicts,
            "price_sources": self.price_sources,
            "narrative": self.narrative,
            "reasoning": self.reasoning,
        }


@dataclass
class FusionEngineConfig:
    """Configuration for fusion behavior."""

    # If true, fusion can downgrade Execute -> Watch/Pass; never upgrades
    allow_verdict_downgrade: bool = True

    # If true, a high-confidence intent can modulate the score of a direction.
    # Until calibrated, intent runs in log-only mode by default.
    allow_intent_modulation: bool = False

    # Minimum visual pattern confidence required to log a conflict.
    visual_override_threshold: float = 0.80

    # Margin required for one direction to win over the other.
    # If the score ratio is inside [1 - margin, 1 + margin], result is contested.
    contested_margin: float = 0.15

    # Confidence reduction when layers conflict
    conflict_confidence_penalty: float = 0.85


from smc_desk.rules import load_rule_config

class FusionEngine:
    """Score two engine-owned directions and select or contest the result."""

    def __init__(self, config: Optional[FusionEngineConfig] = None):
        self.config = config or FusionEngineConfig()
        
        # Enforce global authority limit
        rule_config = load_rule_config()
        if getattr(rule_config, "vision_authority_mode", "observe_only") == "observe_only":
            self.config.allow_verdict_downgrade = False
            self.config.allow_intent_modulation = False

    def fuse(
        self,
        engine_result: AnalysisResult,
        sequence_memory: SequenceMemory,
        intent_result: Optional[IntentResult] = None,
        visual_patterns: Optional[list[dict[str, Any]]] = None,
        context: Optional[Any] = None,
    ) -> FusionResult:
        """Produce a fused recommendation from the engine's dual plans and context layers."""
        visual_patterns = visual_patterns or []
        primary_plan = engine_result.trade_plan
        bullish_plan = engine_result.bullish_plan
        bearish_plan = engine_result.bearish_plan

        overrides: list[FusionOverride] = []
        contributions: list[FusionContribution] = []
        conflicts: list[str] = []

        # Record engine contribution for the primary direction.
        contributions.append(
            FusionContribution(
                layer="engine",
                verdict=primary_plan.verdict,
                bias=primary_plan.direction,
                confidence=primary_plan.confidence,
                notes="Deterministic SMC engine; owns all prices.",
            )
        )

        # Gather candidate plans. A Pass verdict means hard gates failed; it is
        # not a candidate for selection.
        candidates: dict[str, TradePlan] = {}
        if bullish_plan and bullish_plan.verdict != "Pass":
            candidates["bullish"] = bullish_plan
        if bearish_plan and bearish_plan.verdict != "Pass":
            candidates["bearish"] = bearish_plan

        # Compute raw scores from engine confluence.
        raw_scores: dict[str, float] = {
            direction: plan.confluence_score for direction, plan in candidates.items()
        }

        # REGIME MODULATION: chop and trend-counter regimes lower confidence.
        regime = getattr(context, "regime_label", "unknown")
        if regime == "chop":
            for direction in raw_scores:
                raw_scores[direction] *= 0.7
            conflicts.append("Regime is chop; trend-following setups are penalized.")
        elif regime == "trend_counter":
            for direction in raw_scores:
                raw_scores[direction] *= 0.8
            conflicts.append("Regime is trend_counter; setup fights HTF bias.")

        # INTENT MODULATION (log-only by default until calibrated).
        # A trap/distribution intent lowers the score of the affected direction.
        # It never asserts a direction on its own.
        if intent_result is not None:
            intent_bias = self._intent_bias(intent_result.primary_intent)
            contributions.append(
                FusionContribution(
                    layer="intent",
                    verdict="Watch",
                    bias=intent_bias,
                    confidence=intent_result.confidence,
                    notes=intent_result.reasoning,
                )
            )

            if self.config.allow_intent_modulation:
                bearish_penalty_intents = {
                    MarketIntent.BULL_TRAP,
                    MarketIntent.SMART_MONEY_DISTRIBUTING,
                    MarketIntent.BULLISH_EXHAUSTION,
                }
                bullish_penalty_intents = {
                    MarketIntent.BEAR_TRAP,
                    MarketIntent.SMART_MONEY_ACCUMULATING,
                    MarketIntent.BEARISH_EXHAUSTION,
                }

                if intent_result.primary_intent in bearish_penalty_intents:
                    if "bullish" in raw_scores:
                        old_score = raw_scores["bullish"]
                        raw_scores["bullish"] *= 0.7
                        overrides.append(
                            FusionOverride(
                                source="intent",
                                field="bullish_score",
                                old_value=str(round(old_score, 4)),
                                new_value=str(round(raw_scores["bullish"], 4)),
                                reason=f"{intent_result.primary_intent.value} modulates bullish score.",
                                confidence=intent_result.confidence,
                            )
                        )
                elif intent_result.primary_intent in bullish_penalty_intents:
                    if "bearish" in raw_scores:
                        old_score = raw_scores["bearish"]
                        raw_scores["bearish"] *= 0.7
                        overrides.append(
                            FusionOverride(
                                source="intent",
                                field="bearish_score",
                                old_value=str(round(old_score, 4)),
                                new_value=str(round(raw_scores["bearish"], 4)),
                                reason=f"{intent_result.primary_intent.value} modulates bearish score.",
                                confidence=intent_result.confidence,
                            )
                        )
            else:
                # Log-only: record that intent would have modulated but is not allowed.
                conflicts.append(
                    f"Intent {intent_result.primary_intent.value} detected at "
                    f"confidence {intent_result.confidence:.4f}; modulation disabled until calibrated."
                )

        # SEQUENCE OVERRIDE: active trap blocks execution regardless of other signals.
        if sequence_memory.active_episode and sequence_memory.active_episode.episode_type.value == "trap":
            overrides.append(
                FusionOverride(
                    source="sequence",
                    field="verdict",
                    old_value="Execute",
                    new_value="Watch",
                    reason="Active trap episode blocks execution until resolved.",
                    confidence=0.85,
                )
            )
            if self.config.allow_verdict_downgrade:
                conflicts.append("Active trap episode downgrades any Execute to Watch.")

        # VISUAL CONFLICT LOGGING (vision never asserts direction or prices).
        for pattern in visual_patterns:
            conf = pattern.get("confidence", 0.0)
            if conf < self.config.visual_override_threshold:
                continue
            invalidates = pattern.get("invalidates_bias")
            if invalidates:
                conflicts.append(
                    f"Visual pattern {pattern.get('pattern_type')} conflicts with {invalidates} bias "
                    f"(conf {conf:.2f})."
                )

        # Select direction.
        recommended_direction = "neutral"
        recommended_verdict = "Pass"
        recommended_grade = "C"
        fused_confidence = 0.0
        contested = False

        if not raw_scores:
            recommended_verdict = "Pass"
            recommended_grade = "C"
            fused_confidence = 0.0
        elif len(raw_scores) == 1:
            recommended_direction = next(iter(raw_scores))
            plan = candidates[recommended_direction]
            recommended_verdict = self._apply_trap_downgrade(plan.verdict)
            recommended_grade = plan.setup_grade
            fused_confidence = plan.confidence
        else:
            bullish_score = raw_scores["bullish"]
            bearish_score = raw_scores["bearish"]
            total = bullish_score + bearish_score
            if total > 0:
                bullish_ratio = bullish_score / total
                bearish_ratio = bearish_score / total
                margin = self.config.contested_margin
                if 0.5 - margin / 2 < bullish_ratio < 0.5 + margin / 2:
                    contested = True
                    recommended_direction = "neutral"
                    recommended_verdict = "Watch"
                    recommended_grade = "C"
                    fused_confidence = round(max(bullish_plan.confidence, bearish_plan.confidence) * 0.8, 4)
                elif bullish_score > bearish_score:
                    recommended_direction = "bullish"
                    plan = candidates["bullish"]
                    recommended_verdict = self._apply_trap_downgrade(plan.verdict)
                    recommended_grade = plan.setup_grade
                    fused_confidence = plan.confidence
                else:
                    recommended_direction = "bearish"
                    plan = candidates["bearish"]
                    recommended_verdict = self._apply_trap_downgrade(plan.verdict)
                    recommended_grade = plan.setup_grade
                    fused_confidence = plan.confidence

        # Apply conflict confidence penalty.
        if conflicts:
            fused_confidence *= self.config.conflict_confidence_penalty
        fused_confidence = max(0.0, min(0.95, fused_confidence))

        # Price provenance: every price we might reference must come from an engine plan.
        price_sources = self._build_price_sources(bullish_plan, bearish_plan)

        # Build plan summaries.
        bullish_summary = self._plan_summary(bullish_plan) if bullish_plan else {}
        bearish_summary = self._plan_summary(bearish_plan) if bearish_plan else {}

        narrative = sequence_memory.get_current_narrative()
        reasoning = self._generate_reasoning(
            primary_plan,
            recommended_direction,
            recommended_verdict,
            contested,
            overrides,
            conflicts,
        )

        return FusionResult(
            engine_primary_verdict=primary_plan.verdict,
            engine_primary_bias=primary_plan.direction,
            engine_primary_grade=primary_plan.setup_grade,
            engine_primary_confidence=primary_plan.confidence,
            bullish_plan_summary=bullish_summary,
            bearish_plan_summary=bearish_summary,
            scores=raw_scores,
            recommended_direction=recommended_direction,
            recommended_verdict=recommended_verdict,
            recommended_grade=recommended_grade,
            fused_confidence=round(fused_confidence, 4),
            contested=contested,
            overrides=overrides,
            contributions=contributions,
            conflicts=conflicts,
            price_sources=price_sources,
            narrative=narrative,
            reasoning=reasoning,
        )

    def _apply_trap_downgrade(self, verdict: str) -> str:
        if self.config.allow_verdict_downgrade and verdict == "Execute":
            return "Watch"
        return verdict

    @staticmethod
    def _plan_summary(plan: TradePlan) -> dict[str, Any]:
        return {
            "direction": plan.direction,
            "verdict": plan.verdict,
            "grade": plan.setup_grade,
            "confluence_score": round(plan.confluence_score, 4),
            "confidence": round(plan.confidence, 4),
            "entry_zone": FusionEngine._format_zone(plan.entry_low, plan.entry_high),
            "invalidation": plan.invalidation,
            "target": plan.liquidity_target,
            "risk_reward": plan.risk_reward,
        }

    @staticmethod
    def _format_zone(low: float | None, high: float | None) -> str:
        if low is None or high is None:
            return "N/A"
        return f"{low:.5f} - {high:.5f}"

    @staticmethod
    def _build_price_sources(bullish_plan: TradePlan | None, bearish_plan: TradePlan | None) -> dict[str, str]:
        """Map every referenced price to its source plan/direction."""
        sources: dict[str, str] = {}

        def add(plan: TradePlan, label: str) -> None:
            for price in (plan.entry_low, plan.entry_high, plan.invalidation, plan.liquidity_target):
                if price is not None:
                    sources[str(price)] = f"{plan.direction} {label}"
            for target in plan.targets:
                sources[str(target)] = f"{plan.direction} target"

        if bullish_plan:
            add(bullish_plan, "plan")
        if bearish_plan:
            add(bearish_plan, "plan")
        return sources

    @staticmethod
    def _intent_bias(intent: MarketIntent) -> str:
        bullish_intents = {
            MarketIntent.GENUINE_BULLISH_TREND,
            MarketIntent.BEAR_TRAP,
            MarketIntent.BEARISH_EXHAUSTION,
            MarketIntent.SMART_MONEY_ACCUMULATING,
        }
        bearish_intents = {
            MarketIntent.GENUINE_BEARISH_TREND,
            MarketIntent.BULL_TRAP,
            MarketIntent.BULLISH_EXHAUSTION,
            MarketIntent.SMART_MONEY_DISTRIBUTING,
        }
        if intent in bullish_intents:
            return "bullish"
        if intent in bearish_intents:
            return "bearish"
        return "neutral"

    def _generate_reasoning(
        self,
        primary_plan: TradePlan,
        recommended_direction: str,
        recommended_verdict: str,
        contested: bool,
        overrides: list[FusionOverride],
        conflicts: list[str],
    ) -> str:
        lines = [
            f"Engine primary: {primary_plan.verdict} / {primary_plan.direction} / grade {primary_plan.setup_grade}.",
        ]
        if contested:
            lines.append(
                f"Fused recommendation: contested → {recommended_verdict}. "
                "Neither direction won by a clear margin."
            )
        else:
            lines.append(
                f"Fused recommendation: {recommended_verdict} / {recommended_direction} / grade {primary_plan.setup_grade}."
            )
        if overrides:
            lines.append("Overrides:")
            for o in overrides:
                lines.append(f"  - {o.source}: {o.field} {o.old_value} -> {o.new_value} ({o.reason})")
        if conflicts:
            lines.append("Conflicts:")
            for c in conflicts:
                lines.append(f"  - {c}")
        if not overrides and not conflicts:
            lines.append("No overrides or conflicts: engine dual plans drive the recommendation.")
        return " ".join(lines)
