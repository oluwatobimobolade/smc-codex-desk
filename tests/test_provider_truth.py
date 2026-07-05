"""Test that provider truth is honest.

The system must never auto-label a local callable as REAL_VISION_LLM_PROVIDER.
Every provider must declare its mode explicitly. Local deterministic providers
must be marked as such, not as real LLM calls.
"""
from __future__ import annotations

import pytest

from smc_desk.brain.llm_provider import (
    CallableAISMCProvider,
    LLMCompletionRequest,
    StubAISMCProvider,
)


def _dummy_fn(request: LLMCompletionRequest) -> dict:
    return {"schema": "ai_smc_trader_decision_v1", "symbol": "BTCUSDT"}


def test_callable_requires_explicit_provider_mode() -> None:
    """CallableAISMCProvider must require provider_mode — no auto-labeling."""
    with pytest.raises(TypeError):
        CallableAISMCProvider(_dummy_fn, provider_name="x", model_name="y")


def test_callable_rejects_invalid_provider_mode() -> None:
    """Invalid provider_mode values must be rejected."""
    with pytest.raises(ValueError, match="provider_mode must be one of"):
        CallableAISMCProvider(
            _dummy_fn,
            provider_name="x",
            model_name="y",
            provider_mode="FAKE_MODE",
        )


def test_callable_rejects_legacy_is_stub_kwarg() -> None:
    """The old is_stub kwarg must not be accepted."""
    with pytest.raises(TypeError):
        CallableAISMCProvider(
            _dummy_fn,
            provider_name="x",
            model_name="y",
            is_stub=False,
        )


def test_local_deterministic_provider_is_not_real_reasoning() -> None:
    """LOCAL_DETERMINISTIC_PROVIDER must NOT be marked as real reasoning."""
    provider = CallableAISMCProvider(
        _dummy_fn,
        provider_name="local_codex_thread_brain",
        model_name="conservative_template",
        provider_mode="LOCAL_DETERMINISTIC_PROVIDER",
    )
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "LOCAL_DETERMINISTIC_PROVIDER"
    assert result.is_real_reasoning is False
    assert result.is_real_llm_call is False
    assert result.is_stub is False
    assert result.metadata["provider_mode_explicit"] is True


def test_manual_ai_assisted_is_real_reasoning_not_real_llm() -> None:
    """MANUAL_AI_ASSISTED_JSON is real reasoning (human/chat) but NOT an LLM API call."""
    provider = CallableAISMCProvider(
        _dummy_fn,
        provider_name="chat_assistant_ai_brain",
        model_name="this_chat_with_vision",
        provider_mode="MANUAL_AI_ASSISTED_JSON",
    )
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "MANUAL_AI_ASSISTED_JSON"
    assert result.is_real_reasoning is True
    assert result.is_real_llm_call is False
    assert result.is_manual is True


def test_real_vision_llm_provider_is_real() -> None:
    """REAL_VISION_LLM_PROVIDER is both real reasoning and a real LLM call."""
    provider = CallableAISMCProvider(
        _dummy_fn,
        provider_name="openai_gpt4v",
        model_name="gpt-4-vision",
        provider_mode="REAL_VISION_LLM_PROVIDER",
    )
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "REAL_VISION_LLM_PROVIDER"
    assert result.is_real_reasoning is True
    assert result.is_real_llm_call is True
    assert result.is_manual is False


def test_stub_provider_is_not_real() -> None:
    """STUB_PROVIDER must never be marked as real."""
    provider = StubAISMCProvider({"x": 1})
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    assert result.provider_mode == "STUB_PROVIDER"
    assert result.is_real_reasoning is False
    assert result.is_real_llm_call is False
    assert result.is_stub is True


def test_audit_record_reflects_provider_mode() -> None:
    """The audit record must show the true provider mode, not auto-label."""
    provider = CallableAISMCProvider(
        _dummy_fn,
        provider_name="local_codex_thread_brain",
        model_name="conservative_template",
        provider_mode="LOCAL_DETERMINISTIC_PROVIDER",
    )
    request = LLMCompletionRequest(prompt="test", evidence_pack={}, chart_images={})
    result = provider.complete(request)
    audit = result.audit_record()
    assert audit["provider_mode"] == "LOCAL_DETERMINISTIC_PROVIDER"
    assert audit["is_real_llm_call"] is False
    assert audit["is_real_reasoning"] is False
    assert "REAL_LLM_PROVIDER" not in str(audit)
