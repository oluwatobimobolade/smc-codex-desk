from __future__ import annotations

from smc_desk.colleague.smc_narrative_authority import build_smc_narrative_authority
from smc_desk.rendering.watch_chart_renderer import render_watch_chart
from wp0029_fixtures import sample_cognitive, sample_df


def test_official_chart_uses_narrative_authority(tmp_path):
    authority = build_smc_narrative_authority(symbol="BTCUSDT", cognitive_result=sample_cognitive())
    out = tmp_path / "official_watch.png"

    render_watch_chart(sample_df(), authority, out)

    assert out.exists()
    assert authority["chart_template"] == "watch_chart"
    assert authority["show_trade_box"] is False
