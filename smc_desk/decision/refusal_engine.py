"""Central refusal policy for the colleague cognitive pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RefusalDecision:
    final_action: str
    perception_allowed: bool
    signal_allowed: bool
    reasons: list[str] = field(default_factory=list)
    blocking_codes: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return self.final_action in {"REFUSE_PERCEPTION", "NO_SIGNAL"}

    def to_dict(self) -> dict:
        return {
            "final_action": self.final_action,
            "perception_allowed": self.perception_allowed,
            "signal_allowed": self.signal_allowed,
            "refused": self.refused,
            "reasons": list(self.reasons),
            "blocking_codes": list(self.blocking_codes),
        }


def evaluate_refusal(
    *,
    truth_report: Any,
    regime_assessment: Any | None = None,
    contradiction_resolution: Any | None = None,
    uncertainty_assessment: Any | None = None,
) -> RefusalDecision:
    """Apply hard gates in priority order."""
    reasons: list[str] = []
    blocking_codes: list[str] = []

    if not getattr(truth_report, "ok", False):
        for issue in getattr(truth_report, "issues", []):
            code = getattr(issue, "code", "market_truth_failure")
            if code not in blocking_codes:
                blocking_codes.append(code)
        reasons.append("Market truth failed; perception output is refused.")
        return RefusalDecision(
            final_action="REFUSE_PERCEPTION",
            perception_allowed=False,
            signal_allowed=False,
            reasons=reasons,
            blocking_codes=blocking_codes,
        )

    if regime_assessment is not None and float(getattr(regime_assessment, "confidence", 0.0) or 0.0) < 0.60:
        reasons.append("Regime confidence below 0.60.")
        blocking_codes.append("low_regime_confidence")

    if contradiction_resolution is not None:
        outcome = getattr(contradiction_resolution, "outcome", "WAIT")
        if outcome == "INVALIDATE_ALL":
            reasons.append("Higher-timeframe contradiction invalidates the setup.")
            blocking_codes.append("contradiction_invalidates_all")
        elif outcome == "WAIT":
            reasons.append("Timeframe evidence is unresolved; wait.")
            blocking_codes.append("timeframe_contradiction_wait")

    if uncertainty_assessment is not None and float(getattr(uncertainty_assessment, "signal_confidence", 0.0) or 0.0) < 0.60:
        reasons.append("Signal confidence below 0.60.")
        blocking_codes.append("low_signal_confidence")

    if blocking_codes:
        return RefusalDecision(
            final_action="NO_SIGNAL",
            perception_allowed=True,
            signal_allowed=False,
            reasons=reasons,
            blocking_codes=blocking_codes,
        )

    return RefusalDecision(
        final_action="OBSERVE_ONLY",
        perception_allowed=True,
        signal_allowed=False,
        reasons=["Cognitive checks passed, but execution authority remains disabled."],
        blocking_codes=[],
    )
