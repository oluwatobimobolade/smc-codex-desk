from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from wp0029_fixtures import sample_cognitive


def test_continuation_conditions_written():
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=sample_cognitive())

    text = " ".join(authority["continuation_confirmed_if"])
    assert "retests active 15m supply" in text
    assert "breaks the next sell-side liquidity" in text
