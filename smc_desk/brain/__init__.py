"""AI SMC trader brain contracts.

The brain package is local-first. It defines the evidence, schema, and
validation boundary for model-assisted SMC reasoning, but it does not call an
external model API or authorize execution.
"""

from smc_desk.brain.ai_smc_consistency_validator import (
    ValidationIssue,
    ValidationResult,
    validate_ai_smc_decision,
)
from smc_desk.brain.ai_smc_trader_brain import (
    AISMCDecision,
    AISMCTraderBrain,
    REASONING_ORDER,
    build_ai_smc_prompt,
    parse_ai_smc_decision,
)
from smc_desk.brain.llm_provider import CallableAISMCProvider, LLMCompletionRequest, LLMCompletionResult, StubAISMCProvider
from smc_desk.brain.prompt_system import build_prompt_registry_manifest, prompt_system_hash
from smc_desk.brain.providers.manual_provider import ManualJSONProvider
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack

__all__ = [
    "AISMCDecision",
    "AISMCTraderBrain",
    "REASONING_ORDER",
    "CallableAISMCProvider",
    "LLMCompletionRequest",
    "LLMCompletionResult",
    "ManualJSONProvider",
    "StubAISMCProvider",
    "build_prompt_registry_manifest",
    "prompt_system_hash",
    "ValidationIssue",
    "ValidationResult",
    "build_ai_smc_prompt",
    "build_smc_evidence_pack",
    "parse_ai_smc_decision",
    "validate_ai_smc_decision",
]
