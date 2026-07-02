from __future__ import annotations

from pathlib import Path

from smc_desk.colleague.wp0020_gauntlet import (
    assert_thesis_evidence_links,
    generate_evidence_linked_smc_thesis,
)


def _cognitive_result() -> dict:
    return {
        "final_action": "NO_SIGNAL",
        "regime": {
            "structure_regime": "ranging",
            "volatility_regime": "compression",
            "liquidity_regime": "accumulation",
            "confidence": 0.72,
        },
        "contradiction": {
            "outcome": "WAIT",
            "dominant_direction": "bullish",
        },
        "uncertainty": {
            "signal_confidence": 0.55,
            "final_verdict": "NO_SIGNAL",
        },
        "refusal": {
            "final_action": "NO_SIGNAL",
            "signal_allowed": False,
            "blocking_codes": ["timeframe_contradiction_wait"],
        },
    }


def test_smc_thesis_has_evidence_for_every_claim_and_no_signal_language(tmp_path):
    thesis = generate_evidence_linked_smc_thesis(
        symbol="BTCUSDT",
        cognitive_result=_cognitive_result(),
        annotation_manifest={
            "annotations": [
                {
                    "event_id": "15m:event:0:BOS",
                    "timestamp": "2026-06-27T00:00:00+00:00",
                    "price": 100_000,
                }
            ]
        },
        visual_reconciliation={"status": "REVIEW_REQUIRED"},
        output_dir=tmp_path,
    )

    assert thesis["status"] == "PASS"
    assert thesis["final_decision"] == "NO_SIGNAL"
    assert thesis["forbidden_language_present"] is False
    assert_thesis_evidence_links(thesis)
    assert {claim["claim_id"] for claim in thesis["claims"]} == {
        "market_context",
        "regime",
        "structure_and_poi",
        "contradiction",
        "uncertainty",
        "visual_audit",
        "final_decision",
    }
    for claim in thesis["claims"]:
        assert claim["evidence"]

    assert Path(tmp_path / "smc_trade_thesis.md").exists()
    assert Path(tmp_path / "smc_trade_thesis.json").exists()
    assert Path(tmp_path / "thesis_evidence_map.json").exists()
