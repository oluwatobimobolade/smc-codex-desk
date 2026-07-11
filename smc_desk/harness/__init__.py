"""SMC Codex Desk perception test harness (programme §19, §29).

Synthetic case generators, metamorphic relations, and counterfactual
mutations for testing the deterministic structure machines and validators
against ground truth rather than only internal consistency.
"""
from smc_desk.harness import counterfactual, metamorphic, synthetic

__all__ = ["counterfactual", "metamorphic", "synthetic"]