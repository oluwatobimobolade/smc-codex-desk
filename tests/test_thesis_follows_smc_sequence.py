from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from smc_desk.colleague.smc_thesis_v5 import REQUIRED_SEQUENCE, assert_smc_thesis_v5_quality, build_smc_thesis_v5
from wp0029_fixtures import sample_cognitive


def test_thesis_follows_smc_sequence():
    cognitive = sample_cognitive()
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=cognitive)
    thesis = build_smc_thesis_v5(symbol="BTCUSDT", cognitive_result=cognitive, narrative_authority=authority)

    assert thesis["schema"] == "smc_thesis_v5"
    assert thesis["claim_sequence"] == REQUIRED_SEQUENCE
    assert thesis["show_trade_box"] is False
    assert_smc_thesis_v5_quality(thesis)
