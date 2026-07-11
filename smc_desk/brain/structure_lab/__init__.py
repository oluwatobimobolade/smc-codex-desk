"""Governed AI-first SMC structure research laboratory."""

from smc_desk.brain.structure_lab.annotation_bridge import resolve_semantic_annotation_plan
from smc_desk.brain.structure_lab.runtime import CallableRoleProvider, ReplayRoleProvider, run_structure_lab

__all__ = ["CallableRoleProvider", "ReplayRoleProvider", "resolve_semantic_annotation_plan", "run_structure_lab"]
