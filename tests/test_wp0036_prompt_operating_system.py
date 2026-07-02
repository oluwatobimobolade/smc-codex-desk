from __future__ import annotations

import json

from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER, build_ai_smc_prompt
from smc_desk.brain.prompt_system import build_prompt_registry_manifest, load_prompt_modules
from smc_desk.brain.prompt_system.prompt_contract import PromptModule


def _prompt_payload() -> dict:
    return json.loads(
        build_ai_smc_prompt(
            {
                "schema": "smc_evidence_pack_v1",
                "symbol": "BTCUSDT",
                "chart_images": {"15m": {"path": "chart.png"}},
                "detector_candidates": {},
                "provenance": {"pack_hash": "abc"},
            }
        )
    )


def _prompt_text() -> str:
    payload = _prompt_payload()
    module_text = "\n".join(module["text"] for module in payload["prompt_system"]["modules"])
    return json.dumps(payload, sort_keys=True) + "\n" + module_text


def test_prompt_contains_reasoning_order():
    payload = _prompt_payload()
    assert payload["required_reasoning_order"] == REASONING_ORDER
    text = _prompt_text()
    for item in ("daily_context", "4h_context", "1h_context", "active_range", "model_completion_liquidity_target"):
        assert item in json.dumps(payload)


def test_prompt_contains_user_doctrine():
    text = _prompt_text().lower()
    assert "daily -> 4h -> 1h -> 15m" in text
    assert "external structure has authority over internal noise" in text
    assert "being correct about direction is not enough" in text
    assert "prefer a correct no-trade" in text


def test_prompt_forbids_1m_entries():
    text = _prompt_text().lower()
    assert "1m is forbidden" in text
    assert "no 1m official entry" in text


def test_prompt_forbids_risk_or_position_sizing():
    text = _prompt_text().lower()
    for forbidden in ("account risk", "leverage", "position sizing", "liquidation", "partial closes", "breakeven", "trailing"):
        assert forbidden in text


def test_prompt_requires_model_completion_target():
    text = _prompt_text().lower()
    assert "model-completion liquidity" in text
    assert "targets must be model-completion liquidity" in text
    assert "not nearest tiny 15m levels" in text


def test_prompt_requires_structural_invalidation():
    text = _prompt_text().lower()
    assert "stop loss is structural invalidation" in text
    assert "stop loss must equal structural invalidation" in text
    assert "do not use arbitrary tight stops" in text


def test_prompt_requires_no_trade_for_weak_setups():
    text = _prompt_text().lower()
    assert "do not force trades" in text
    assert "reject weak setups" in text
    assert "missed_trade_no_chase" in text
    assert "valid_direction_bad_rr_wait_for_better_entry" in text


def test_prompt_forbids_trade_ready_without_valid_displacement():
    text = _prompt_text().lower()
    assert "trade_plan_ready is forbidden when displacement_assessment is none/weak/review" in text
    assert "structure_broken=true" in text
    assert "planned entry without a proven displacement is a watch" in text


def test_prompt_requires_watch_state_without_trade_box():
    text = _prompt_text().lower()
    assert "watch charts must not show entry, sl, tp, rr trade box" in text
    assert "if not trade_plan_ready" in text
    assert "annotation_plan.show_trade_box must be false" in text


def test_prompt_requires_active_range_authority_and_self_review():
    payload = _prompt_payload()
    text = _prompt_text().lower()
    assert "active_range_authority.selected_range" in text
    assert "do not use ohlcv summary highs/lows" in text
    assert "second pass" in text
    assert "self_review" in payload["required_json_schema"]["fields"]
    assert "mandatory_self_review" in payload


def test_prompt_requires_strict_json_schema():
    payload = _prompt_payload()
    assert payload["required_json_schema"]["schema"] == "ai_smc_trader_decision_v1"
    assert payload["required_json_schema"]["strict_json_only"] is True
    text = _prompt_text().lower()
    assert "return strict json only" in text
    assert "no markdown" in text
    assert "annotation_plan.reasoning_order must exactly equal required_reasoning_order" in text


def test_prompt_version_hash_changes_on_edit():
    original = PromptModule(
        name="test_prompt",
        version="1.0.0",
        purpose="test",
        text="Use top-down context.",
    )
    edited = PromptModule(
        name="test_prompt",
        version="1.0.0",
        purpose="test",
        text="Use top-down context and stricter refusal.",
    )
    assert original.hash != edited.hash


def test_prompt_registry_has_versioned_modules():
    manifest = build_prompt_registry_manifest(include_text=False)
    assert manifest["schema"] == "smc_prompt_registry_manifest_v1"
    assert manifest["hash"]
    assert manifest["module_count"] == len(load_prompt_modules())
    for module in manifest["modules"]:
        assert module["name"]
        assert module["version"]
        assert module["purpose"]
        assert module["hash"]
        assert "text" not in module
