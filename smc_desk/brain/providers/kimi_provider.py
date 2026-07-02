from __future__ import annotations

from smc_desk.brain.llm_provider import LLMCompletionRequest, LLMCompletionResult


class KimiProvider:
    provider_name = "Kimi"
    is_stub = False

    def __init__(self, *, model_name: str = "not-configured"):
        self.model_name = model_name

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        raise RuntimeError("KimiProvider is not configured in the local-first no-API workflow.")
