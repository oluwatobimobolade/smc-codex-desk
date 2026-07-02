from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from wp0029_fixtures import sample_cognitive


def test_smc_narrative_authority_selects_one_model():
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=sample_cognitive())

    assert authority["schema"] == "smc_narrative_authority_v2"
    assert authority["official_model"] == "bearish_continuation_watch"
    assert authority["official_bias"] == "bearish"
    assert authority["official_state"] == "WAIT_FOR_RETRACE_TO_SUPPLY"
    assert authority["official_active_poi"]["zone_label"] == "15m supply 100.50-101.00"
    assert authority["chart_template"] == "watch_chart"
