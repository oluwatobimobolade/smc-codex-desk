"""Optional provider adapters for AI SMC brain runs."""

from smc_desk.brain.providers.manual_provider import ManualJSONProvider
from smc_desk.brain.providers.openai_provider import OpenAIProvider
from smc_desk.brain.providers.claude_provider import ClaudeProvider
from smc_desk.brain.providers.kimi_provider import KimiProvider

__all__ = ["ManualJSONProvider", "OpenAIProvider", "ClaudeProvider", "KimiProvider"]
