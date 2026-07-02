from __future__ import annotations

from datetime import datetime, timedelta, timezone

import matplotlib.axes
import pandas as pd

from smc_desk.perception.engine_v2 import PerceptionSnapshot
from smc_desk.render_v2 import render_v2_story_chart


def _df() -> pd.DataFrame:
    start = datetime(2026, 6, 27, tzinfo=timezone.utc)
    rows = []
    price = 60000.0
    for index in range(96):
        ts = start + timedelta(minutes=15 * index)
        close = price + (45 if index % 5 else -90)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": price,
                "high": max(price, close) + 30,
                "low": min(price, close) - 30,
                "close": close,
                "volume": 1000 + index,
            }
        )
        price = close
    return pd.DataFrame(rows)


def _snapshot() -> PerceptionSnapshot:
    now = datetime(2026, 6, 27, 21, 0, tzinfo=timezone.utc)
    return PerceptionSnapshot.model_validate(
        {
            "decision_time": now.isoformat(),
            "swings": {"local": [], "internal": [], "external": []},
            "structure_state": {
                "current_direction": "bearish",
                "protected_high_id": None,
                "protected_low_id": None,
                "last_confirmed_external_high": None,
                "last_confirmed_external_low": None,
                "last_confirmed_internal_high": None,
                "last_confirmed_internal_low": None,
                "last_external_break_id": None,
                "last_internal_break_id": None,
                "internal_direction": "bearish",
                "protected_internal_high_id": None,
                "protected_internal_low_id": None,
                "current_as_of": now.isoformat(),
            },
            "structure_breaks": [],
            "fvgs": [],
            "liquidity_levels": [],
            "sweeps": [],
            "order_blocks": [],
            "inducements": [],
            "poi_grade_fvgs": [],
            "candle_count": 96,
            "last_close": now.isoformat(),
            "last_price": "60100.0",
        }
    )


def test_story_chart_text_names_watch_state_and_parent_poi_warning(monkeypatch, tmp_path):
    captured: list[str] = []
    original_text = matplotlib.axes.Axes.text
    original_title = matplotlib.axes.Axes.set_title

    def capture_text(self, *args, **kwargs):
        if len(args) >= 3:
            captured.append(str(args[2]))
        return original_text(self, *args, **kwargs)

    def capture_title(self, label, *args, **kwargs):
        captured.append(str(label))
        return original_title(self, label, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "text", capture_text)
    monkeypatch.setattr(matplotlib.axes.Axes, "set_title", capture_title)

    render_v2_story_chart(
        _df(),
        _snapshot(),
        {
            "symbol": "BTCUSDT",
            "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
            "final_action": "NO_SIGNAL",
            "watch_state": {
                "final_state": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
                "final_action": "NO_SIGNAL",
                "direction": "bearish",
                "active_poi": None,
                "poi_selection": {
                    "status": "WATCH_NEW_LOWER_SUPPLY_FORMATION",
                    "parent_scope_pois": [
                        {
                            "timeframe": "1h",
                            "kind": "supply",
                            "price_low": "66206.6",
                            "price_high": "66388.8",
                            "rejection_reason": "above protected high",
                        }
                    ],
                },
            },
            "execution_readiness": {"state": "HTF_MODEL_FORMING", "confidence": 0.42},
            "inducement_continuation": {"state": "POSSIBLE_INDUCEMENT", "confidence": 0.48},
            "structure_hierarchy": {
                "15m": {
                    "external_bias": "bearish",
                    "structure_phase": "retracement_inside_bearish_external_range",
                    "depth_status": "sufficient_research_depth",
                    "protected_high": "60924.7",
                    "protected_low": "58030.0",
                    "dealing_range": {
                        "range_high": "60924.7",
                        "range_low": "58030.0",
                        "equilibrium_50": "59477.35",
                    },
                }
            },
            "truth_report": {"timeframe_summaries": [{"timeframe": "15m", "candle_count": 96}]},
            "authority": {"live_execution": "disabled"},
        },
        "15m",
        str(tmp_path / "BTCUSDT_15m_story.png"),
        mode="story",
    )

    text = "\n".join(captured)
    assert "WATCH_NEW_LOWER_SUPPLY_FORMATION" in text
    assert "Readiness: HTF_MODEL_FORMING" in text
    assert "Move quality: POSSIBLE_INDUCEMENT" in text
    assert "Parent 1h supply 66206.6-66388.8 is not active: above protected high" in text
    assert "ACTIVE POI" not in text


def test_story_chart_separates_model_direction_from_ltf_bias(monkeypatch, tmp_path):
    captured_titles: list[str] = []
    original_title = matplotlib.axes.Axes.set_title

    def capture_title(self, label, *args, **kwargs):
        captured_titles.append(str(label))
        return original_title(self, label, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "set_title", capture_title)

    render_v2_story_chart(
        _df(),
        _snapshot(),
        {
            "symbol": "SOLUSDT",
            "final_state": "POI_TOUCHED_AWAIT_15M_CONFIRMATION",
            "final_action": "NO_SIGNAL",
            "watch_state": {
                "final_state": "POI_TOUCHED_AWAIT_15M_CONFIRMATION",
                "final_action": "NO_SIGNAL",
                "direction": "bearish",
                "active_poi": {
                    "poi_id": "4h:supply:test",
                    "timeframe": "4h",
                    "kind": "supply",
                    "price_low": "68.27",
                    "price_high": "70.60",
                    "validity_status": "VALID_ACTIVE_SETUP_POI",
                    "scope": "active_setup",
                },
            },
            "execution_readiness": {"state": "POI_REACHED_AWAIT_CONFIRMATION", "confidence": 0.58},
            "inducement_continuation": {"state": "CONTINUATION_CONFIRMED", "confidence": 0.78},
            "structure_hierarchy": {
                "15m": {
                    "external_bias": "bullish",
                    "structure_phase": "pullback_inside_bullish_external_range",
                    "depth_status": "sufficient_research_depth",
                    "protected_high": "60924.7",
                    "protected_low": "58030.0",
                    "dealing_range": {
                        "range_high": "60924.7",
                        "range_low": "58030.0",
                        "equilibrium_50": "59477.35",
                    },
                }
            },
            "truth_report": {"timeframe_summaries": [{"timeframe": "15m", "candle_count": 96}]},
            "authority": {"live_execution": "disabled"},
        },
        "15m",
        str(tmp_path / "SOLUSDT_15m_story.png"),
        mode="story",
    )

    title = "\n".join(captured_titles)
    assert "model bearish" in title
    assert "15m bias bullish" in title
    assert "POI_TOUCHED_AWAIT_15M_CONFIRMATION" in title
