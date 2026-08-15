import pandas as pd

from smc_desk.brain.ai_smc_consistency_validator import (
    ValidationIssue,
    _check_market_source_identity,
    strip_requested_market_semantics_for_source_mismatch,
    validate_ai_smc_decision,
)
from smc_desk.brain.ai_smc_trader_brain import parse_ai_smc_decision
from smc_desk.brain.llm_provider import LLMCompletionRequest
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.data.source_identity import assess_source_identity
from tools.run_live_ai_smc_full_system import build_conservative_ai_payload


def test_direct_crypto_source_identity_is_verified() -> None:
    certificate = assess_source_identity(
        "ETHUSDT",
        {
            "symbol": "ETHUSDT",
            "source": "binance_usdm_rest",
            "market_type": "USD-M perpetual futures",
        },
    )

    assert certificate["status"] == "VERIFIED"
    assert certificate["candle_authority_allowed"] is True
    assert certificate["trade_promotion_allowed"] is True


def test_direct_yahoo_forex_symbol_suffix_is_equivalent() -> None:
    certificate = assess_source_identity(
        "AUDCAD",
        {
            "symbol": "AUDCAD",
            "provider_symbol": "AUDCAD=X",
            "market_type": "forex_spot_chart_proxy",
        },
    )

    assert certificate["status"] == "VERIFIED"
    assert certificate["provider_symbol_canonical"] == "AUDCAD"


def test_explicit_gold_futures_proxy_cannot_certify_xauusd() -> None:
    certificate = assess_source_identity(
        "XAUUSD",
        {
            "symbol": "XAUUSD",
            "provider_symbol": "GC=F",
            "market_type": "COMEX gold futures proxy",
            "proxy_note": "GC=F is not XAUUSD spot.",
        },
    )

    assert certificate["status"] == "MISMATCH_PROXY"
    assert certificate["candle_authority_allowed"] is False
    assert certificate["trade_promotion_allowed"] is False
    assert certificate["failures"]


def test_unrelated_provider_symbol_fails_closed() -> None:
    certificate = assess_source_identity(
        "HYPEUSDT",
        {
            "symbol": "HYPEUSDT",
            "provider_symbol": "ETHUSDT",
            "market_type": "USD-M perpetual futures",
        },
    )

    assert certificate["status"] == "MISMATCH"
    assert certificate["candle_authority_allowed"] is False


def test_source_identity_mismatch_is_a_hard_validation_issue() -> None:
    issues = []
    _check_market_source_identity(
        {
            "session_context": {
                "source_identity_certificate": {
                    "status": "MISMATCH_PROXY",
                    "failures": ["GC=F is not XAUUSD"],
                }
            }
        },
        issues,
    )

    assert [issue.code for issue in issues] == ["market_source_identity_mismatch"]
    assert issues[0].severity == "hard"


def test_unverified_source_is_warning_without_trade_promotion() -> None:
    issues = []
    _check_market_source_identity(
        {"session_context": {"source_identity_certificate": {"status": "UNVERIFIED"}}},
        issues,
    )

    assert [issue.code for issue in issues] == ["market_source_identity_unverified"]
    assert issues[0].severity == "warning"


def test_mismatched_source_is_quarantined_before_semantic_pack_build() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-08-01", periods=80, freq="15min", tz="UTC"),
            "open": [100.0 + index * 0.1 for index in range(80)],
            "high": [100.4 + index * 0.1 for index in range(80)],
            "low": [99.6 + index * 0.1 for index in range(80)],
            "close": [100.2 + index * 0.1 for index in range(80)],
            "volume": [1000.0] * 80,
        }
    )
    certificate = assess_source_identity(
        "XAUUSD",
        {
            "symbol": "XAUUSD",
            "provider_symbol": "GC=F",
            "market_type": "COMEX gold futures proxy",
            "proxy_note": "GC=F is not XAUUSD spot.",
        },
    )
    pack = build_smc_evidence_pack(
        symbol="XAUUSD",
        timeframe_dfs={"15m": frame},
        detector_candidates={
            "15m": {
                "structure_breaks": [{"object_id": "must-not-survive"}],
                "order_blocks": [{"object_id": "proxy-ob"}],
            }
        },
        session_context={"source_identity_certificate": certificate},
    )

    assert pack["data_contract"]["semantic_market_authority"] is False
    assert pack["source_identity_quarantine"]["active"] is True
    assert pack["active_range_authority"]["status"] == "SOURCE_IDENTITY_WITHHELD"
    assert pack["active_range_authority"]["selected_range"] is None
    assert pack["formal_structure_graph"]["active_range"]["status"] == "UNRESOLVED"
    assert pack["formal_structure_graph"]["active_range"]["current_price"] is None
    assert pack["detector_candidates"]["15m"]["structure_breaks"] == []
    assert pack["detector_candidates"]["15m"]["order_blocks"] == []
    assert pack["market_state"]["structure"]["range_high"] is None
    # Raw rows can be retained for source diagnostics, but are not semantic authority.
    assert pack["ohlcv_windows"]["15m"]

    payload = build_conservative_ai_payload(
        LLMCompletionRequest(prompt="test", evidence_pack=pack, chart_images={}),
        {"source": "test", "symbol": "XAUUSD", "provider_symbol": "GC=F"},
    )
    result = validate_ai_smc_decision(parse_ai_smc_decision(payload), pack)
    assert [issue.code for issue in result.issues if issue.severity == "hard"] == [
        "market_source_identity_mismatch"
    ]
    assert result.smc_model_validity == "invalid"
    assert result.trade_plan_validity == "failed"
    assert result.official_decision["active_range"]["high"] is None
    assert result.official_decision["annotation_plan_v2"]["objects"] == []


def test_source_mismatch_sanitizer_removes_all_proxy_market_claims() -> None:
    issue = ValidationIssue(
        code="market_source_identity_mismatch",
        severity="hard",
        message="GC=F is not XAUUSD.",
    )
    official = {
        "symbol": "XAUUSD",
        "official_state": "WATCH_ONLY",
        "direction": "bullish",
        "active_range": {"high": 4509.1, "low": 4373.9},
        "entry_plan": {"entry_ready": False, "entry_price": None},
        "stop_loss_plan": {"stop_price": None},
        "target_plan": {"targets": []},
        "rr_status": {"minimum_rr": 3.0},
        "invalidation": {"invalidation_price": 4373.9},
        "annotation_plan": {
            "chart_template": "watch_chart",
            "show_trade_box": False,
            "labels": [{"text": "bullish"}],
            "levels": [{"price": 4509.1}],
        },
        "annotation_plan_v2": {"objects": [{"object_type": "range_zone"}]},
    }

    stripped = strip_requested_market_semantics_for_source_mismatch(official, [issue])

    assert stripped["official_state"] == "REVIEW_REQUIRED"
    assert stripped["direction"] == "mixed"
    assert stripped["active_range"]["high"] is None
    assert stripped["active_range"]["low"] is None
    assert stripped["invalidation"]["invalidation_price"] is None
    assert stripped["annotation_plan"]["levels"] == []
    assert stripped["annotation_plan_v2"]["objects"] == []
    assert "analysis unavailable" in stripped["final_thesis"].lower()
