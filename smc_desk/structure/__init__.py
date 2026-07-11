"""SMC structure state machines (programme §5, §6, §7, §8, §9).

Public surface:
- doctrine           -- constitution loader + integrity check
- protected_point    -- causal protected-point state machine (§5)
- active_range       -- active dealing-range state machine (§7)
- level_interactions -- sweep/breakout/probe/reclaim multi-horizon state
                        machine (§6)
- poi_ranker         -- POI three-score ranker (deterministic + AI semantic +
                        empirical) with combined_rank + uncertainty (§8)
- inducement         -- inducement hypothesis state machine, five necessary
                        conditions, falsifiable (§9)
"""
from smc_desk.structure.active_range import (
    RangeDirection,
    RangeLifecycle,
    RangeObject,
    ReplacementTrigger,
    activate,
    can_replace,
    location_in_range,
    propose_range,
    replace,
)
from smc_desk.structure.doctrine import (
    DEFAULT_DOCTRINE_PATH,
    DEFAULT_HASH_PATH,
    DoctrineLoad,
    concept,
    doctrine,
    is_authoritative,
    load_doctrine,
    missing_structural_fields,
    unresolved_contested_decisions,
)
from smc_desk.structure.inducement import (
    InducementHypothesis,
    InducementState,
    confirm_consumption,
    evaluate,
)
from smc_desk.structure.level_interactions import (
    Horizon,
    InteractionType,
    LevelInteraction,
    LevelInteractionReport,
    build_report,
    classify_at_event,
    is_wick_only,
    refine_at_horizon,
)
from smc_desk.structure.poi_ranker import (
    POIScores,
    attach_ai_semantic,
    deterministic_score,
    score_pois,
)
from smc_desk.structure.protected_point import (
    ProtectedPointCandidate,
    ProtectedPointSelection,
    generate_candidates,
    score_candidates,
    select,
)

__all__ = [
    "DEFAULT_DOCTRINE_PATH",
    "DEFAULT_HASH_PATH",
    "DoctrineLoad",
    "Horizon",
    "InducementHypothesis",
    "InducementState",
    "InteractionType",
    "LevelInteraction",
    "LevelInteractionReport",
    "POIScores",
    "ProtectedPointCandidate",
    "ProtectedPointSelection",
    "RangeDirection",
    "RangeLifecycle",
    "RangeObject",
    "ReplacementTrigger",
    "activate",
    "attach_ai_semantic",
    "build_report",
    "can_replace",
    "classify_at_event",
    "confirm_consumption",
    "concept",
    "deterministic_score",
    "doctrine",
    "evaluate",
    "generate_candidates",
    "is_authoritative",
    "is_wick_only",
    "load_doctrine",
    "location_in_range",
    "missing_structural_fields",
    "propose_range",
    "refine_at_horizon",
    "replace",
    "score_candidates",
    "score_pois",
    "select",
    "unresolved_contested_decisions",
]
