from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from wp0029_fixtures import sample_cognitive


def test_sol_current_case_wait_for_retrace():
    authority = build_smc_narrative_authority(
        symbol="SOLUSDT",
        cognitive_result=sample_cognitive(
            symbol="SOLUSDT",
            readiness_state="MOVE_STARTED_NOT_CHASEABLE",
            move_state="MOVE_STARTED_NOT_CHASEABLE",
            watch_state="WATCH_NEW_LOWER_SUPPLY_FORMATION",
            active_poi=None,
        ),
    )

    assert authority["official_model"] == "bearish_continuation_watch"
    assert authority["official_state"] == "MOVE_STARTED_NOT_CHASEABLE"
    assert authority["chart_template"] == "watch_chart"
    assert authority["show_trade_box"] is False
