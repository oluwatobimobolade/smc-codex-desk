"""Isolated facade for the experimental hybrid perception programme.

The facade gives the research path a stable public name without changing or
importing it from the canonical :class:`PerceptionEngineV2` implementation.
It is permanently observe-only until a later governed promotion changes the
authority contract outside this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from smc_desk.brain.structure_lab.runtime import StructureRoleProvider
from smc_desk.perception.candidates.atlas import AtlasConfig
from smc_desk.perception.experimental_break_engine import (
    BreakLevel,
    BreakLifecycleConfig,
    BreakLifecycleResult,
    ExperimentalBreakLifecycleEngine,
)
from smc_desk.perception.programme_run import PerceptionRunEnvelope, run_perception_programme

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class HybridPerceptionEngineV3ExperimentalResult:
    """Source-labelled result with an explicit non-authority contract."""

    envelope: PerceptionRunEnvelope
    schema: str = "hybrid_perception_engine_v3_experimental_result_v1"
    engine: str = "HybridPerceptionEngineV3Experimental"
    baseline_comparator: str = "PerceptionEngineV2"
    runtime_classification: str = "experimental_research_observe_only"
    canonical: bool = False
    promotion_status: str = "NOT_PROMOTED"
    signal_allowed: bool = False
    paper_execution_allowed: bool = False
    live_execution_allowed: bool = False
    predictive_edge_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["authority_contract"] = {
            "canonical": self.canonical,
            "signal_allowed": self.signal_allowed,
            "paper_execution_allowed": self.paper_execution_allowed,
            "live_execution_allowed": self.live_execution_allowed,
            "predictive_edge_claim_allowed": self.predictive_edge_claim_allowed,
            "critic_may_promote": False,
        }
        return payload


class HybridPerceptionEngineV3Experimental:
    """Stable entry point for atlas -> AI panel -> validator research runs.

    No provider is created implicitly. A governed role provider may be
    injected, or an explicitly labelled replay interpretation may be supplied.
    With neither, the underlying programme abstains.
    """

    canonical_baseline = "PerceptionEngineV2"
    authority_contract = {
        "canonical": False,
        "signal_allowed": False,
        "paper_execution_allowed": False,
        "live_execution_allowed": False,
        "predictive_edge_claim_allowed": False,
        "critic_may_promote": False,
    }

    def __init__(
        self,
        *,
        fill_budget: int = 600,
        break_config: BreakLifecycleConfig | None = None,
    ) -> None:
        if fill_budget < 0:
            raise ValueError("fill_budget must be non-negative")
        self.fill_budget = fill_budget
        self.break_lifecycle = ExperimentalBreakLifecycleEngine(break_config)

    def classify_break(
        self,
        *,
        level: BreakLevel,
        candles: list[Mapping[str, Any]],
        atr: float,
        decision_time: str,
    ) -> BreakLifecycleResult:
        """Expose V2-constitution break semantics without changing canonical V2."""
        return self.break_lifecycle.classify(
            level=level,
            candles=candles,
            atr=atr,
            decision_time=decision_time,
        )

    def run(
        self,
        *,
        case: Mapping[str, Any],
        decision_time: str,
        per_timeframe_cutoff: Mapping[str, str] | None = None,
        timeframe_dfs: Mapping[str, "pd.DataFrame"] | None = None,
        atlas_configs: Mapping[str, AtlasConfig] | None = None,
        candidate_pool: list[Mapping[str, Any]] | None = None,
        role_provider: StructureRoleProvider | None = None,
        role_output_dir: str | Path | None = None,
        annotation_renderer: Callable[[Mapping[str, Any], Mapping[str, Any], Path], Mapping[str, Any]] | None = None,
        interpretation: Mapping[str, Any] | None = None,
        candidate_overrides: set[str] | None = None,
    ) -> HybridPerceptionEngineV3ExperimentalResult:
        envelope = run_perception_programme(
            case=case,
            decision_time=decision_time,
            per_timeframe_cutoff=per_timeframe_cutoff,
            timeframe_dfs=timeframe_dfs,
            atlas_configs=atlas_configs,
            candidate_pool=candidate_pool,
            role_provider=role_provider,
            role_output_dir=role_output_dir,
            annotation_renderer=annotation_renderer,
            interpretation=interpretation,
            candidate_overrides=candidate_overrides,
            fill_budget=self.fill_budget,
        )
        return HybridPerceptionEngineV3ExperimentalResult(envelope=envelope)


__all__ = [
    "HybridPerceptionEngineV3Experimental",
    "HybridPerceptionEngineV3ExperimentalResult",
]
