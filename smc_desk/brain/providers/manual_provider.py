from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smc_desk.brain.llm_provider import LLMCompletionRequest, LLMCompletionResult


class ManualJSONProvider:
    """Provider for no-API local operation.

    It returns a supplied JSON payload and can be marked real only when the
    payload came from an actual chart-reading workflow outside this process.
    Tests should keep fixed payloads as stub/non-real.
    """

    def __init__(
        self,
        payload: str | Mapping[str, Any],
        *,
        provider_name: str = "manual_local_ai_workspace",
        model_name: str = "manual-json",
        is_real_reasoning: bool = False,
    ):
        self.payload = payload
        self.provider_name = provider_name
        self.model_name = model_name
        self.is_stub = not is_real_reasoning
        self.is_real_reasoning = is_real_reasoning
        self.last_request: LLMCompletionRequest | None = None

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        self.last_request = request
        payload = self.payload
        if "colleague" in str(request.prompt).lower() or "veto" in str(request.prompt).lower():
            payload = {
                "veto": False,
                "critique": "SMC setup conforms to all core requirements and structural parameters.",
                "suggested_downgrade_state": "KEEP_CURRENT"
            }
        return LLMCompletionResult(
            raw_json=payload,
            provider_name=self.provider_name,
            model_name=self.model_name,
            is_stub=self.is_stub,
            is_real_reasoning=self.is_real_reasoning,
            provider_mode="MANUAL_AI_ASSISTED_JSON",
            is_manual=True,
            is_real_llm_call=False,
            api_usage={"prompt_tokens": 0, "completion_tokens": 0, "image_count": len(request.chart_images)},
            prompt_hash=request.prompt_hash,
            evidence_hash=request.evidence_hash,
            chart_image_count=len(request.chart_images),
            metadata={"adapter": "manual_json", "api_usage": "none"},
        )
