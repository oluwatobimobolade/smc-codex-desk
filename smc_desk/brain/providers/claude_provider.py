from __future__ import annotations

from smc_desk.brain.llm_provider import LLMCompletionRequest, LLMCompletionResult


class ClaudeProvider:
    provider_name = "Claude"
    is_stub = False

    def __init__(self, *, model_name: str = "not-configured"):
        self.model_name = model_name

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        raise RuntimeError("ClaudeProvider is not configured in the local-first no-API workflow.")
