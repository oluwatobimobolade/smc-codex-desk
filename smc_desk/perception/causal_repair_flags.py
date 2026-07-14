"""Reversible feature flags for the WP-SMC-10 canonical causal-OB-origin repair.

These flags gate the promotion of already-built shadow machinery (displacement
scoring, causal protected-point selection, causal OB-origin gate) onto the
canonical PerceptionEngineV2 path. Each flag defaults OFF so the WP-SMC-10
commits can ship the new code paths without changing behaviour until the
cutover commit flips the defaults ON.

Read at call time (not import time) so tests can toggle via ``monkeypatch.setenv``.

Authority note: these flags only change *deterministic classification and lineage*
on the canonical path. They never touch ``authority_contract`` -- signal/paper/live
execution remain disabled regardless of flag state.
"""
from __future__ import annotations

import os

_ENV_DISPLACEMENT = "SMC_CANONICAL_DISPLACEMENT_SCORING"
_ENV_PROTECTED_POINT = "SMC_CAUSAL_PROTECTED_POINT"
_ENV_ORIGIN_GATE = "SMC_CAUSAL_OB_ORIGIN_GATE"


def canonical_displacement_scoring_enabled() -> bool:
    """When True, confirmed structure breaks carry a real displacement_strength
    (scored via smc_desk.perception.displacement.score_break_displacement) instead
    of the legacy hardcoded 0.0."""
    return os.environ.get(_ENV_DISPLACEMENT, "0") == "1"


def causal_protected_point_enabled() -> bool:
    """When True, _confirm_break selects protected_high/low via the causal-necessity
    algorithm (smc_desk.structure.protected_point.select) and falls back to the
    legacy last_confirmed_* assignment only when the algorithm abstains."""
    return os.environ.get(_ENV_PROTECTED_POINT, "0") == "1"


def causal_ob_origin_gate_enabled() -> bool:
    """When True, order_blocks._find_origin_cluster admits an origin cluster only
    when its departure produced measured displacement into the accepted break."""
    return os.environ.get(_ENV_ORIGIN_GATE, "0") == "1"


__all__ = [
    "canonical_displacement_scoring_enabled",
    "causal_protected_point_enabled",
    "causal_ob_origin_gate_enabled",
]