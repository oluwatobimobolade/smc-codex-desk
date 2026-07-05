"""External AI Agent provider.

This provider reads a response from an external AI agent (Codex, Gemini
Antigravity, ChatGPT, Kimi, etc.) and returns it as the decision.

The provider is honest about what it is:
  - provider_mode = "EXTERNAL_AI_AGENT"
  - is_real_reasoning = True (the agent really did reason)
  - is_real_llm_call = False (the system did not call an LLM API)
  - is_manual = False (a human did not type the JSON)

The system validates the response, grounds the levels, and renders the chart.
The agent's role is reasoning, not execution.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smc_desk.brain.llm_provider import LLMCompletionRequest, LLMCompletionResult


class ExternalAIAgentProvider:
    """Provider that reads a pre-written agent response.

    The response must be a dict (or JSON string) matching the
    ai_smc_trader_decision_v1 schema. The provider wraps it in an
    LLMCompletionResult with provider_mode='EXTERNAL_AI_AGENT'.
    """

    provider_name = "external_ai_agent"
    model_name = "external_agent_response"
    is_stub = False

    def __init__(
        self,
        response_payload: str | Mapping[str, Any],
        *,
        agent_name: str = "unknown_agent",
        agent_model: str = "unknown_model",
        provider_name: str | None = None,
        model_name: str | None = None,
        packet_hash: str | None = None,
    ):
        self.response_payload = response_payload
        self.agent_name = agent_name
        self.agent_model = agent_model
        if provider_name:
            self.provider_name = provider_name
        if model_name:
            self.model_name = model_name
        self.packet_hash = packet_hash
        self.last_request: LLMCompletionRequest | None = None

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        self.last_request = request
        if isinstance(self.response_payload, str):
            import json
            raw = json.loads(self.response_payload)
        else:
            raw = dict(self.response_payload)
        if "agent_identity" not in raw:
            raw["agent_identity"] = {
                "agent_name": self.agent_name,
                "agent_model": self.agent_model,
                "packet_hash": self.packet_hash or "",
                "imported_via": "external_ai_agent_provider",
            }
        return LLMCompletionResult(
            raw_json=raw,
            provider_name=self.provider_name,
            model_name=self.model_name,
            is_stub=False,
            is_real_reasoning=True,
            provider_mode="EXTERNAL_AI_AGENT",
            is_manual=False,
            is_real_llm_call=False,
            api_usage={"prompt_tokens": 0, "completion_tokens": 0, "image_count": len(request.chart_images)},
            prompt_hash=request.prompt_hash,
            evidence_hash=request.evidence_hash,
            chart_image_count=len(request.chart_images),
            metadata={
                "agent_name": self.agent_name,
                "agent_model": self.agent_model,
                "packet_hash": self.packet_hash,
                "imported_via": "external_ai_agent_provider",
            },
        )
