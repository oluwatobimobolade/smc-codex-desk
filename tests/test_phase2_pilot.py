"""
Phase 2 Tests: Config propagation, Jaccard formula, and annotation schema validation.
"""
import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone


class TestConfigPropagation:
    """Verify that changing YAML values propagates through the full chain."""
    
    def test_swing_scales_load_from_yaml(self):
        """RuleConfig.swing_scales must match PERCEPTION_ONTOLOGY_V2.yaml exactly."""
        from smc_desk.rules import load_rule_config
        config = load_rule_config()
        
        assert config.swing_scales.local == 1
        assert config.swing_scales.internal == 3
        assert config.swing_scales.external == 5
    
    def test_multi_scale_detector_uses_config(self):
        """MultiScaleSwingDetector must use config values, not hardcoded ones."""
        from smc_desk.rules import RuleConfig, SwingScales
        from smc_desk.perception.swings import MultiScaleSwingDetector
        
        # Create a config with non-default values
        custom_config = RuleConfig(
            swing_scales=SwingScales(local=2, internal=4, external=7)
        )
        detector = MultiScaleSwingDetector(config=custom_config)
        
        # Verify detectors use custom values
        scale_map = {d.scale_name: d for d in detector.detectors}
        assert scale_map["local"].bars_left == 2
        assert scale_map["local"].bars_right == 2
        assert scale_map["internal"].bars_left == 4
        assert scale_map["internal"].bars_right == 4
        assert scale_map["external"].bars_left == 7
        assert scale_map["external"].bars_right == 7
    
    def test_perception_engine_propagates_config(self):
        """PerceptionEngineV2 must pass its config to its swing detector."""
        from smc_desk.rules import RuleConfig, SwingScales
        from smc_desk.perception.engine_v2 import PerceptionEngineV2
        
        custom_config = RuleConfig(
            swing_scales=SwingScales(local=2, internal=4, external=6)
        )
        engine = PerceptionEngineV2(config=custom_config)
        
        # Verify config is stored
        assert engine.config.swing_scales.local == 2
        assert engine.config.swing_scales.internal == 4
        
        # Verify detectors use the custom scales
        scale_map = {d.scale_name: d for d in engine.swing_detector.detectors}
        assert scale_map["local"].bars_left == 2
        assert scale_map["external"].bars_left == 6
    
    def test_default_config_matches_yaml(self):
        """Default RuleConfig() should produce values matching the YAML file."""
        from smc_desk.rules import RuleConfig
        
        config = RuleConfig()
        assert config.ontology_version == "2.0.0"
        assert config.risk_reward_floor == 3.0
        assert config.vision_authority_mode == "observe_only"
        assert config.fvg.minimum_gap_bps == 5.0
    
    def test_extra_fields_rejected(self):
        """RuleConfig must reject unknown/legacy fields."""
        from smc_desk.rules import RuleConfig
        
        with pytest.raises(Exception):  # Pydantic ValidationError
            RuleConfig(pivot_window=3)  # Legacy field
        
        with pytest.raises(Exception):
            RuleConfig(internal_pivot_window=2)  # Legacy field

    def test_legacy_strategy_json_loads_through_adapter(self):
        """Persisted research JSON should migrate through load_rule_config, not RuleConfig."""
        from smc_desk.rules import load_rule_config

        config = load_rule_config("strategies/smc/rules_widthfloor.json")

        assert config.swing_scales.local == 3
        assert config.swing_scales.internal == 2
        assert config.swing_scales.external == 3
        assert config.equal_level_tolerance_bps == 15.0
        assert config.fvg.minimum_gap_bps == 5.0
        assert config.structure_break_min_bps == 4.0
        assert config.structural_stop_margin_bps == 10.0
        assert config.min_poi_width_bps == 25.0


class TestJaccardFormula:
    """Verify the Jaccard consistency formula is mathematically correct."""
    
    def test_perfect_agreement(self):
        """When both reviewers agree on everything, Jaccard should be 1.0."""
        from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator
        
        evaluator = HumanChallengeEvaluator()
        cases = [{"case_id": "CASE-001"}]
        
        annos = [
            {"case_id": "CASE-001", "primitive": "swing_high", "direction": "bearish",
             "timestamp": "2024-01-01T00:00:00Z", "price": 100.0}
        ]
        
        result = evaluator.run_blind_challenge(
            cases=cases,
            human_annotations={"rev_a": annos.copy(), "rev_b": annos.copy()},
            ai_annotations=annos.copy()
        )
        
        assert result["consistency_jaccard"] == 1.0
        assert result["ai_jaccard_vs_consensus"] == 1.0
        assert result["ai_precision"] == 1.0
        assert result["ai_recall"] == 1.0
        assert result["ai_f1"] == 1.0
    
    def test_no_agreement(self):
        """When reviewers disagree completely, Jaccard should be 0.0."""
        from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator
        
        evaluator = HumanChallengeEvaluator()
        cases = [{"case_id": "CASE-001"}]
        
        annos_a = [{"case_id": "CASE-001", "primitive": "swing_high", "direction": "bearish",
                     "timestamp": "2024-01-01T00:00:00Z", "price": 100.0}]
        annos_b = [{"case_id": "CASE-001", "primitive": "swing_low", "direction": "bullish",
                     "timestamp": "2024-06-01T00:00:00Z", "price": 50.0}]
        
        result = evaluator.run_blind_challenge(
            cases=cases,
            human_annotations={"rev_a": annos_a, "rev_b": annos_b},
            ai_annotations=[]
        )
        
        assert result["consistency_jaccard"] == 0.0
    
    def test_partial_agreement_jaccard(self):
        """Verify Jaccard = |A∩B| / |A∪B| = |A∩B| / (|A| + |B| - |A∩B|)."""
        from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator
        
        evaluator = HumanChallengeEvaluator()
        cases = [{"case_id": "CASE-001"}]
        
        # Rev A: 2 annotations, Rev B: 3 annotations, 1 in common
        shared = {"case_id": "CASE-001", "primitive": "bos", "direction": "bullish",
                  "timestamp": "2024-01-01T00:00:00Z", "price": 100.0}
        unique_a = {"case_id": "CASE-001", "primitive": "swing_high", "direction": "bearish",
                    "timestamp": "2024-01-02T00:00:00Z", "price": 110.0}
        unique_b1 = {"case_id": "CASE-001", "primitive": "fvg_bullish", "direction": "bullish",
                     "timestamp": "2024-01-03T00:00:00Z", "price": 95.0}
        unique_b2 = {"case_id": "CASE-001", "primitive": "sweep", "direction": "bearish",
                     "timestamp": "2024-01-04T00:00:00Z", "price": 90.0}
        
        annos_a = [shared, unique_a]  # |A| = 2
        annos_b = [shared.copy(), unique_b1, unique_b2]  # |B| = 3
        
        result = evaluator.run_blind_challenge(
            cases=cases,
            human_annotations={"rev_a": annos_a, "rev_b": annos_b},
            ai_annotations=[]
        )
        
        # Jaccard = 1 / (2 + 3 - 1) = 1/4 = 0.25
        assert result["consistency_jaccard"] == 0.25
    
    def test_ai_precision_recall(self):
        """Verify Precision and Recall are computed correctly."""
        from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator
        
        evaluator = HumanChallengeEvaluator()
        cases = [{"case_id": "C1"}]
        
        gold = {"case_id": "C1", "primitive": "bos", "direction": "bullish",
                "timestamp": "2024-01-01T00:00:00Z", "price": 100.0}
        missed = {"case_id": "C1", "primitive": "choch", "direction": "bearish",
                  "timestamp": "2024-02-01T00:00:00Z", "price": 80.0}
        false_alarm = {"case_id": "C1", "primitive": "sweep", "direction": "bullish",
                       "timestamp": "2024-03-01T00:00:00Z", "price": 120.0}
        
        # Both reviewers agree on gold + missed → consensus = [gold, missed]
        human = [gold, missed]
        # AI finds gold + false_alarm → TP=1, FP=1, FN=1
        ai = [gold.copy(), false_alarm]
        
        result = evaluator.run_blind_challenge(
            cases=cases,
            human_annotations={"rev_a": human, "rev_b": human.copy()},
            ai_annotations=ai
        )
        
        # TP=1, FP=1, FN=1
        assert result["ai_precision"] == 0.5  # 1/(1+1)
        assert result["ai_recall"] == 0.5     # 1/(1+1)

    def test_empty_consensus_is_not_scored_as_perfect(self):
        """No labels and no AI output means insufficient evidence, not 100% accuracy."""
        from smc_desk.evaluation.human_challenge import HumanChallengeEvaluator

        evaluator = HumanChallengeEvaluator()
        result = evaluator.run_blind_challenge(
            cases=[{"case_id": "C1"}],
            human_annotations={"rev_a": [], "rev_b": []},
            ai_annotations=[],
        )

        assert result["consistency_jaccard"] is None
        assert result["consensus_label_count"] == 0
        assert result["ai_evaluation_status"] == "insufficient_consensus"
        assert result["ai_precision"] is None


class TestAnnotationSchema:
    """Verify the annotation schema validates correctly."""
    
    def test_valid_annotation(self):
        from smc_desk.evaluation.annotation_schema import StructuralAnnotation
        
        anno = StructuralAnnotation(
            case_id="CASE-001",
            reviewer_id="reviewer_00",
            primitive="swing_high",
            direction="bearish",
            scope="internal",
            timestamp="2024-01-01T00:00:00+00:00",
            price=100.5,
            confidence=0.85
        )
        assert anno.case_id == "CASE-001"
        assert anno.confidence == 0.85
    
    def test_invalid_timestamp_rejected(self):
        from smc_desk.evaluation.annotation_schema import StructuralAnnotation
        
        with pytest.raises(Exception):
            StructuralAnnotation(
                case_id="CASE-001",
                reviewer_id="reviewer_00",
                primitive="bos",
                direction="bullish",
                timestamp="not-a-date",
                price=100.0
            )
    
    def test_extra_fields_rejected(self):
        from smc_desk.evaluation.annotation_schema import StructuralAnnotation
        
        with pytest.raises(Exception):
            StructuralAnnotation(
                case_id="CASE-001",
                reviewer_id="reviewer_00",
                primitive="bos",
                direction="bullish",
                timestamp="2024-01-01T00:00:00Z",
                price=100.0,
                random_field="should_fail"
            )
    
    def test_negative_price_rejected(self):
        from smc_desk.evaluation.annotation_schema import StructuralAnnotation
        
        with pytest.raises(Exception):
            StructuralAnnotation(
                case_id="CASE-001",
                reviewer_id="reviewer_00",
                primitive="bos",
                direction="bullish",
                timestamp="2024-01-01T00:00:00Z",
                price=-50.0
            )
    
    def test_bundle_loading(self):
        from smc_desk.evaluation.annotation_schema import CaseAnnotationBundle, load_annotations_from_directory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = {
                "case_id": "CASE-001",
                "reviewer_id": "reviewer_00",
                "annotations": [
                    {
                        "case_id": "CASE-001",
                        "reviewer_id": "reviewer_00",
                        "primitive": "swing_high",
                        "direction": "bearish",
                        "timestamp": "2024-01-01T00:00:00Z",
                        "price": 100.0
                    }
                ]
            }
            with open(Path(tmpdir) / "CASE-001_annotations.json", "w") as f:
                json.dump(bundle, f)
            
            bundles = load_annotations_from_directory(tmpdir)
            assert len(bundles) == 1
            assert bundles[0].case_id == "CASE-001"
            assert len(bundles[0].annotations) == 1
