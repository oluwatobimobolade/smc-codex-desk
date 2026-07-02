from __future__ import annotations

from smc_desk.colleague.wp0020_gauntlet import _confidence_summary


def test_pipeline_confidence_can_be_high_while_analysis_confidence_is_low():
    summary = _confidence_summary(
        {
            "06_cognitive": {
                "uncertainty": {
                    "pipeline_confidence": 0.92,
                    "analysis_confidence": 0.50,
                    "context_confidence": 0.40,
                },
                "watch_state": {
                    "active_poi": None,
                },
                "execution_readiness": {
                    "state": "HTF_MODEL_FORMING",
                    "confidence": 0.35,
                },
            },
            "08_visual_reconciliation": {
                "status": "VISUAL_CONTEXT_UNVERIFIED",
            },
        }
    )

    assert summary["pipeline_confidence"] == 0.92
    assert summary["poi_confidence"] == 0.0
    assert summary["visual_confidence"] == 0.0
    assert summary["analysis_confidence"] < summary["pipeline_confidence"]
    assert summary["final_confidence_label"] in {"VERY_LOW_ANALYSIS_CONFIDENCE", "LOW_ANALYSIS_CONFIDENCE"}
