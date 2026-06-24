import pytest
import pandas as pd
from smc_desk.teacher_panel.chart_annotator import ChartAnnotator
from smc_desk.knowledge.rule_cards import RuleCard

def test_source_grounding_trial():
    """Stage 10: Source-Grounding Trial Test
    Verify that every generated label explicitly cites the underlying source rule.
    """
    annotator = ChartAnnotator()
    
    # Create sample DataFrame that triggers an FVG
    data = {
        "open": [100.0, 101.0, 102.0],
        "high": [100.5, 101.5, 105.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.0, 101.0, 104.0]
    }
    df = pd.DataFrame(data)

    rule = RuleCard(
        rule_id="RULE_FVG_001",
        concept="FVG",
        description="A three-candle pattern where candle 1 high is below candle 3 low.",
        academy="Test Academy",
        exact_definition="Test Definition",
        wick_versus_close_rule="wick",
        source_records=[],
        is_active=True
    )

    proposals, execution = annotator.generate_candidate_annotations(df, rule)
    
    assert len(proposals) > 0
    for p in proposals:
        assert "source_rule_id" in p
        assert p["source_rule_id"] == "RULE_FVG_001"

def test_source_grounding_trial_bos():
    """Stage 10: Ensure BOS proposals also cite source rule."""
    annotator = ChartAnnotator()
    
    data = {
        "open": [100, 101, 102, 103, 104, 105],
        "high": [101, 102, 103, 104, 105, 110],
        "low": [99, 100, 101, 102, 103, 104],
        "close": [100, 101, 102, 103, 104, 109]
    }
    df = pd.DataFrame(data)

    rule = RuleCard(
        rule_id="RULE_BOS_001",
        concept="BOS",
        description="A break of structure.",
        academy="Test Academy",
        exact_definition="Test Definition",
        wick_versus_close_rule="close",
        source_records=[],
        is_active=True
    )

    proposals, execution = annotator.generate_candidate_annotations(df, rule)
    
    assert len(proposals) > 0
    for p in proposals:
        assert "source_rule_id" in p
        assert p["source_rule_id"] == "RULE_BOS_001"
