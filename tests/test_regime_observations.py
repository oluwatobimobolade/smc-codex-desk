from __future__ import annotations

import numpy as np
import pandas as pd

from smc_desk.perception.regime_observations import observe_regime_features


def _frame() -> pd.DataFrame:
    index = np.arange(96, dtype=float)
    close = 100 + index * 0.08 + np.sin(index / 3.0) * 1.5
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) + 0.45 + (index % 5) * 0.02
    low = np.minimum(open_, close) - 0.40 - (index % 3) * 0.02
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_regime_output_is_observational_not_participant_intent():
    result = observe_regime_features(_frame())
    assert result["data_status"] == "AVAILABLE"
    assert result["participant_intent_inferred"] is False
    assert result["accumulation_distribution_inferred"] is False
    assert result["signal_allowed"] is False
    assert set(result["descriptive_states"]) == {
        "price_path", "range_behavior", "wick_rejection", "sweep_proxy_activity"
    }
    state_text = " ".join(result["descriptive_states"].values()).lower()
    assert "accumulation" not in state_text
    assert "distribution" not in state_text


def test_features_are_invariant_to_positive_scale_and_translation():
    frame = _frame()
    baseline = observe_regime_features(frame)
    scaled = frame * 7.0
    translated = frame + 2500.0
    assert observe_regime_features(scaled)["features"] == baseline["features"]
    assert observe_regime_features(translated)["features"] == baseline["features"]
    assert observe_regime_features(scaled)["descriptive_states"] == baseline["descriptive_states"]
    assert observe_regime_features(translated)["descriptive_states"] == baseline["descriptive_states"]


def test_short_or_invalid_data_fails_explicitly():
    short = observe_regime_features(_frame().head(10))
    assert short["data_status"] == "INSUFFICIENT"
    broken = _frame()
    broken.loc[0, "high"] = broken.loc[0, "low"] - 1
    invalid = observe_regime_features(broken)
    assert invalid["data_status"] == "FAILED"
    assert "impossible_ohlc_geometry" in invalid["reason_codes"]
