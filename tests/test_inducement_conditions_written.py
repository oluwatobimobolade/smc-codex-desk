from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from wp0029_fixtures import sample_cognitive


def test_inducement_conditions_written():
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=sample_cognitive())

    text = " ".join(authority["inducement_confirmed_if"])
    assert "reclaims above active 15m supply" in text
    assert "holds above" in text
