from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import assert_narrative_authority_contract, build_smc_narrative_authority
from wp0029_fixtures import sample_cognitive


def test_watch_state_blocks_trade_box():
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=sample_cognitive())

    assert authority["official_trade_plan_state"] == "WATCH_ONLY"
    assert authority["show_trade_box"] is False
    assert authority["entry"] is None
    assert authority["stop_loss"] is None
    assert authority["take_profit"] == []
    assert_narrative_authority_contract(authority)
