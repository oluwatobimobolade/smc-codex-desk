import pytest
import pandas as pd
from smc_desk.prediction.abstention_gate import AbstentionGate
from smc_desk.prediction.competing_risk_model import CompetingRiskDiscreteHazardModel
from smc_desk.prediction.event_dataset import EventDatasetBuilder
from smc_desk.prediction.matched_controls import MatchedControlGenerator
from smc_desk.prediction.uncertainty import UncertaintyQuantifier
from smc_desk.prediction.outcome_contract import PredictionContract

def test_abstention_gate_rejections():
    gate = AbstentionGate(max_ood_score=1.0, max_disagreement=0.10, min_effective_samples=100)
    
    # 1. Out of Scope
    res = gate.evaluate_decision({"in_scope": False})
    assert res == "OUT_OF_SCOPE"
    
    # 2. Insufficient Context
    res = gate.evaluate_decision({"in_scope": True, "perception_status": "unvalidated"})
    assert res == "INSUFFICIENT_CONTEXT"
    
    # 3. Low Sample Support
    res = gate.evaluate_decision({
        "in_scope": True, 
        "perception_status": "validated",
        "effective_similar_cases": 50
    })
    assert res == "LOW_SAMPLE_SUPPORT"
    
    # 4. Model Disagreement
    res = gate.evaluate_decision({
        "in_scope": True, 
        "perception_status": "validated",
        "effective_similar_cases": 150,
        "model_disagreement": 0.20
    })
    assert res == "MODEL_DISAGREEMENT"
    
    # 5. OOD
    res = gate.evaluate_decision({
        "in_scope": True, 
        "perception_status": "validated",
        "effective_similar_cases": 150,
        "model_disagreement": 0.05,
        "ood_score": 2.5
    })
    assert res == "UNCALIBRATED_REGIME"
    
    # 6. Negative Expectancy
    res = gate.evaluate_decision({
        "in_scope": True, 
        "perception_status": "validated",
        "effective_similar_cases": 150,
        "model_disagreement": 0.05,
        "ood_score": 0.5,
        "expected_r_lower_95": -0.1
    })
    assert res == "NEGATIVE_EXPECTANCY"
    
    # 7. Actionable (Paper Shadow)
    res = gate.evaluate_decision({
        "in_scope": True, 
        "perception_status": "validated",
        "effective_similar_cases": 150,
        "model_disagreement": 0.05,
        "ood_score": 0.5,
        "expected_r_lower_95": 0.2
    })
    assert res == "PAPER_SHADOW_ONLY"

def test_uncertainty_quantifier():
    p_lower = UncertaintyQuantifier.calculate_p_target_lower_95(p_target=0.41, n_effective_samples=438)
    assert 0.35 < p_lower < 0.41  # Approx 0.36
    
    expected_r = UncertaintyQuantifier.calculate_expected_r_lower_95(
        p_target_lower_95=0.36, 
        p_stop_upper_95=0.45, 
        target_r=3.0, 
        stop_r=-1.0
    )
    assert abs(expected_r - 0.63) < 0.01

def test_prediction_contract_validation():
    # Valid contract
    contract = PredictionContract(
        setup_id="BTCUSDT-15M-2026-00182",
        perception_status="validated",
        state="RETRACE_CONFIRMED",
        regime="TREND_EXPANSION",
        in_scope=True,
        target="external_buy_side_liquidity",
        invalidation="protected_low",
        horizon_bars=32,
        p_target_first=0.41,
        p_stop_first=0.37,
        p_unresolved=0.22,
        p_target_lower_95=0.32,
        expected_r=0.48,
        expected_r_lower_95=0.17,
        effective_similar_cases=438,
        calibration_bin_observed_rate=0.40,
        brier_score_recent=0.19,
        model_disagreement=0.04,
        ood_score=0.08,
        decision="PAPER_SHADOW_ONLY",
        reason="Positive lower-bound expectancy after costs"
    )
    assert contract.setup_id == "BTCUSDT-15M-2026-00182"


def test_prediction_contract_rejects_probability_partition_errors():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        PredictionContract(
            setup_id="bad",
            perception_status="validated",
            state="RETRACE_CONFIRMED",
            regime="TREND_EXPANSION",
            in_scope=True,
            target="external_buy_side_liquidity",
            invalidation="protected_low",
            horizon_bars=32,
            p_target_first=0.50,
            p_stop_first=0.40,
            p_unresolved=0.40,
            p_target_lower_95=0.32,
            expected_r=0.48,
            expected_r_lower_95=0.17,
            effective_similar_cases=438,
            calibration_bin_observed_rate=0.40,
            brier_score_recent=0.19,
            model_disagreement=0.04,
            ood_score=0.08,
            decision="PAPER_SHADOW_ONLY",
            reason="Invalid partition",
        )


def test_event_dataset_requires_mutually_exclusive_outcomes():
    builder = EventDatasetBuilder()

    with pytest.raises(ValueError, match="Exactly one outcome"):
        builder.record_candidate(
            setup_id="s1",
            timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
            state="POI_ACTIVE",
            features={},
            outcome_target=True,
            outcome_stop=False,
            outcome_unresolved=True,
        )

    builder.record_candidate(
        setup_id="s1",
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        state="POI_ACTIVE",
        features={"volatility_percentile": 0.5},
        outcome_target=True,
        outcome_stop=False,
        outcome_unresolved=False,
    )
    assert len(builder.get_dataset()) == 1


def test_matched_controls_select_real_non_smc_row_without_random_outcomes():
    market_data = pd.DataFrame(
        [
            {
                "setup_id": "control_far",
                "is_smc_setup": False,
                "volatility_percentile": 0.90,
                "trend_slope": 0.30,
                "session": "asia",
                "target_first": False,
                "stop_first": True,
                "unresolved": False,
            },
            {
                "setup_id": "control_near",
                "is_smc_setup": False,
                "volatility_percentile": 0.51,
                "trend_slope": 0.02,
                "session": "ny",
                "target_first": True,
                "stop_first": False,
                "unresolved": False,
            },
        ]
    )
    generator = MatchedControlGenerator(market_data)

    control = generator.generate_control_for_setup(
        {"setup_id": "setup", "volatility_percentile": 0.50, "trend_slope": 0.0, "session": "ny"}
    )

    assert control["setup_id"] == "control_near"
    assert control["target_first"] is True
    assert control["stop_first"] is False
    assert control["unresolved"] is False


def test_competing_risk_model_outputs_fitted_probability_partition():
    class FakeHazardModel:
        classes_ = [0, 1, 2]

        def fit(self, X, y):
            return self

        def predict_proba(self, X):
            feature = float(X.iloc[0]["feature"])
            if feature < 0.5:
                return [[0.70, 0.20, 0.10]]
            return [[0.60, 0.10, 0.30]]

    model = CompetingRiskDiscreteHazardModel(max_horizon_bars=4, hazard_model=FakeHazardModel())
    X = pd.DataFrame(
        {
            "feature": [0.0, 0.2, 0.4, 1.0, 1.2, 1.4],
            "horizon_step": [1, 2, 3, 1, 2, 3],
        }
    )
    y = pd.Series([0, 1, 2, 0, 1, 2])

    model.fit(X, y)
    probs = model.predict_cumulative_incidence(pd.DataFrame({"feature": [0.1, 1.1]}))

    assert list(probs.columns) == ["p_target_first", "p_stop_first", "p_unresolved"]
    assert len(probs) == 2
    assert all(abs(row.sum() - 1.0) < 1e-6 for _, row in probs.iterrows())
    assert probs.loc[0, "p_target_first"] > probs.loc[1, "p_target_first"]
