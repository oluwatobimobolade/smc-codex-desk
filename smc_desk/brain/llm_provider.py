"""Provider boundary for the AI SMC trader brain.

Providers are deliberately thin. They receive the exact prompt, structured
evidence pack, and chart-image manifest, then return raw strict JSON plus audit
metadata. Stub providers are useful for tests, but must never be reported as
real chart reasoning.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMCompletionRequest:
    prompt: str
    evidence_pack: Mapping[str, Any]
    chart_images: Mapping[str, Any]
    prompt_version: str = "ai_smc_trader_prompt_v1"

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()

    @property
    def evidence_hash(self) -> str | None:
        provenance = self.evidence_pack.get("provenance") if isinstance(self.evidence_pack, Mapping) else None
        if isinstance(provenance, Mapping):
            raw = provenance.get("pack_hash")
            return str(raw) if raw is not None else None
        return None

    @property
    def chart_image_paths(self) -> list[str]:
        return [
            str(item.get("path"))
            for item in self.chart_images.values()
            if isinstance(item, Mapping) and item.get("exists") and item.get("path")
        ]

    @property
    def chart_image_base64(self) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        for timeframe, item in self.chart_images.items():
            if not isinstance(item, Mapping) or not item.get("base64"):
                continue
            images.append(
                {
                    "timeframe": str(timeframe),
                    "data": str(item["base64"]),
                    "media_type": str(item.get("media_type") or "image/png"),
                    "sha256": str(item.get("sha256") or ""),
                }
            )
        return images


@dataclass(frozen=True)
class LLMCompletionResult:
    raw_json: str | Mapping[str, Any]
    provider_name: str
    model_name: str
    is_stub: bool = False
    is_real_reasoning: bool = True
    provider_mode: str = "REAL_VISION_LLM_PROVIDER"
    api_usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "image_count": 0})
    is_manual: bool = False
    is_real_llm_call: bool = True
    prompt_hash: str | None = None
    evidence_hash: str | None = None
    chart_image_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def audit_record(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "is_stub": self.is_stub,
            "is_real_reasoning": self.is_real_reasoning,
            "provider_mode": self.provider_mode,
            "api_usage": self.api_usage,
            "is_manual": self.is_manual,
            "is_real_llm_call": self.is_real_llm_call,
            "prompt_hash": self.prompt_hash,
            "evidence_hash": self.evidence_hash,
            "chart_image_count": self.chart_image_count,
            "metadata": self.metadata,
        }


class AISMCProvider(Protocol):
    provider_name: str
    model_name: str
    is_stub: bool

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        ...


class StubAISMCProvider:
    provider_name = "STUB_PROVIDER"
    model_name = "stub-json"
    is_stub = True

    def __init__(self, payload: str | Mapping[str, Any]):
        self.payload = payload
        self.last_request: LLMCompletionRequest | None = None

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        self.last_request = request
        return LLMCompletionResult(
            raw_json=self.payload,
            provider_name=self.provider_name,
            model_name=self.model_name,
            is_stub=True,
            is_real_reasoning=False,
            provider_mode="STUB_PROVIDER",
            is_manual=False,
            is_real_llm_call=False,
            api_usage={"prompt_tokens": 0, "completion_tokens": 0, "image_count": 0},
            prompt_hash=request.prompt_hash,
            evidence_hash=request.evidence_hash,
            chart_image_count=len(request.chart_images),
            metadata={"warning": "NOT_REAL_AI_REASONING - STUB_PROVIDER"},
        )


class CallableAISMCProvider:
    """Provider adapter around an injected callable.

    Provider mode is ALWAYS explicit. The caller must declare what kind of
    provider this is — never auto-label as real LLM.

    Valid provider_mode values:
      - REAL_VISION_LLM_PROVIDER: an actual vision LLM (OpenAI, Claude, Kimi, etc.)
        is receiving the prompt + chart images and returning the decision JSON.
      - MANUAL_AI_ASSISTED_JSON: a human or AI assistant (like this chat) has
        inspected the charts and written the JSON. The reasoning is real but
        not from an automated API call.
      - LOCAL_DETERMINISTIC_PROVIDER: a local function is producing a
        conservative/structured payload. This is NOT real AI reasoning.
      - STUB_PROVIDER: a fixed payload. Definitely not real AI reasoning.
    """

    VALID_PROVIDER_MODES = {
        "REAL_VISION_LLM_PROVIDER",
        "EXTERNAL_AI_AGENT",
        "MANUAL_AI_ASSISTED_JSON",
        "LOCAL_DETERMINISTIC_PROVIDER",
        "STUB_PROVIDER",
        "HUMAN_OVERRIDE",
    }

    def __init__(
        self,
        completion_fn,
        *,
        provider_name: str,
        model_name: str,
        provider_mode: str,
    ):
        if provider_mode not in self.VALID_PROVIDER_MODES:
            raise ValueError(
                f"provider_mode must be one of {sorted(self.VALID_PROVIDER_MODES)}, got {provider_mode!r}. "
                "Never auto-label a local callable as REAL_VISION_LLM_PROVIDER."
            )
        self.completion_fn = completion_fn
        self.provider_name = provider_name
        self.model_name = model_name
        self.provider_mode = provider_mode
        self.is_stub = provider_mode in ("STUB_PROVIDER",)
        self.last_request: LLMCompletionRequest | None = None

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        self.last_request = request
        raw = self.completion_fn(request)
        is_real = self.provider_mode in ("REAL_VISION_LLM_PROVIDER", "MANUAL_AI_ASSISTED_JSON", "EXTERNAL_AI_AGENT")
        is_real_call = self.provider_mode == "REAL_VISION_LLM_PROVIDER"
        return LLMCompletionResult(
            raw_json=raw,
            provider_name=self.provider_name,
            model_name=self.model_name,
            is_stub=self.is_stub,
            is_real_reasoning=is_real,
            provider_mode=self.provider_mode,
            is_manual=self.provider_mode == "MANUAL_AI_ASSISTED_JSON",
            is_real_llm_call=is_real_call,
            api_usage={"prompt_tokens": 0, "completion_tokens": 0, "image_count": len(request.chart_images)},
            prompt_hash=request.prompt_hash,
            evidence_hash=request.evidence_hash,
            chart_image_count=len(request.chart_images),
            metadata={"adapter": "callable", "provider_mode_explicit": True},
        )
