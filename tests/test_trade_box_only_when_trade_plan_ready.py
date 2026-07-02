from __future__ import annotations

import pytest

from smc_desk.rendering.trade_plan_chart_renderer import render_trade_plan_chart
from wp0029_fixtures import sample_df


def test_trade_box_only_when_trade_plan_ready(tmp_path):
    df = sample_df()
    watch_authority = {
        "symbol": "BTCUSDT",
        "official_trade_plan_state": "WATCH_ONLY",
        "show_trade_box": False,
    }
    with pytest.raises(ValueError, match="TRADE_PLAN_READY"):
        render_trade_plan_chart(df, watch_authority, tmp_path / "blocked.png")

    ready_authority = {
        "symbol": "BTCUSDT",
        "official_trade_plan_state": "TRADE_PLAN_READY",
        "show_trade_box": True,
        "entry": "100.0",
        "stop_loss": "101.0",
        "take_profit": [{"price": "98.0"}, {"price": "96.0"}],
    }
    out = tmp_path / "trade_plan.png"
    render_trade_plan_chart(df, ready_authority, out)
    assert out.exists()
