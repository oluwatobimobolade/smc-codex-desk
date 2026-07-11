"""SMC Codex Desk — deterministic interpretation validators (programme §28).

Every authoritative interpretation MUST pass the deterministic validators
before it can be CERTIFIED. These checks are deliberately independent of the
AI: they verify that what the AI claims is backed by certified evidence, in
order, with no future data, and that all invariants hold.

The validators are designed so the structure-lab critic role can rely on
them: the critic tries to disprove the interpretation; the validators
guarantee that every cited fact is real.

Public surface (re-exported from smc_desk.validation):
  - Violation, ValidatorResult, validate_interpretation, certify_interpretation
  - evidence_ids, temporal, invariants, narrative (submodules)

Programme sections referenced: §28 (Deterministic validators), §17
(confidence/abstention), §5.2 (graph relationships), §7 (range invariants),
§15 (critic + abstention), §27 (governance).
"""
from smc_desk.validation.validators import (
    Violation,
    ValidatorResult,
    certify_interpretation,
    validate_interpretation,
)
from smc_desk.validation import evidence, invariants, narrative, temporal

__all__ = [
    "Violation",
    "ValidatorResult",
    "certify_interpretation",
    "validate_interpretation",
    "evidence",
    "invariants",
    "narrative",
    "temporal",
]