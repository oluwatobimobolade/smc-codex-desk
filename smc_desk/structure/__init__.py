"""SMC structure state machines (programme §5, §7).

Public surface:
- doctrine           -- constitution loader + integrity check
- protected_point    -- causal protected-point state machine (§5)
- active_range       -- active dealing-range state machine (§7)
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
    "ProtectedPointCandidate",
    "ProtectedPointSelection",
    "RangeDirection",
    "RangeLifecycle",
    "RangeObject",
    "ReplacementTrigger",
    "activate",
    "can_replace",
    "concept",
    "doctrine",
    "generate_candidates",
    "is_authoritative",
    "load_doctrine",
    "location_in_range",
    "missing_structural_fields",
    "propose_range",
    "replace",
    "score_candidates",
    "select",
    "unresolved_contested_decisions",
]
