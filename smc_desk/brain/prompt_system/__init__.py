"""Versioned prompt operating system for the AI SMC trader brain."""

from smc_desk.brain.prompt_system.prompt_builder import build_layered_ai_smc_prompt
from smc_desk.brain.prompt_system.critic_prompt import build_critic_prompt
from smc_desk.brain.prompt_system.prompt_contract import PromptModule
from smc_desk.brain.prompt_system.prompt_registry import (
    PROMPT_SYSTEM_NAME,
    PROMPT_SYSTEM_VERSION,
    build_prompt_registry_manifest,
    load_prompt_modules,
    prompt_system_hash,
)

__all__ = [
    "PROMPT_SYSTEM_NAME",
    "PROMPT_SYSTEM_VERSION",
    "PromptModule",
    "build_layered_ai_smc_prompt",
    "build_critic_prompt",
    "build_prompt_registry_manifest",
    "load_prompt_modules",
    "prompt_system_hash",
]
