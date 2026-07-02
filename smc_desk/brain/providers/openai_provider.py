from __future__ import annotations

from smc_desk.brain.llm_provider import LLMCompletionRequest, LLMCompletionResult


class OpenAIProvider:
    """Optional OpenAI adapter placeholder.

    The project is currently local-first/no-API by default, so this adapter is
    intentionally inert unless a caller subclasses or wraps it with an approved
    API implementation.
    """

    provider_name = "OpenAI"
    is_stub = False

    def __init__(self, *, model_name: str = "not-configured"):
        self.model_name = model_name

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        raise RuntimeError("OpenAIProvider is not configured in the local-first no-API workflow.")
