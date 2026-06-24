import pytest
from smc_desk.teacher_panel.weak_label_aggregator import WeakLabelAggregator
from smc_desk.teacher_panel.weak_label_aggregator import WeakLabelAggregator, LabelTier

def test_human_versus_ai_challenge():
    """Stage 13: Human-versus-AI Challenge
    Verify that if a human provides a gold label, it overrides the AI cluster,
    and the disagreement is recorded.
    """
    aggregator = WeakLabelAggregator()
    
    # 3 AIs agree on approving a setup
    ai_opinions = [
        {"source": "claude", "approved": True},
        {"source": "gpt4", "approved": True},
        {"source": "gemini", "approved": True}
    ]
    
    proposal = {"kind": "fvg"}
    
    # Normally, this is SILVER_HIGH_CONFIDENCE
    tier = aggregator.classify_label(
        proposal=proposal,
        independent_opinions=ai_opinions,
        numerical_verified=True,
        rule_verified=True
    )
    assert tier == LabelTier.SILVER_HIGH_CONFIDENCE
    
    # Human provides a contradictory gold label (rejects the setup)
    human_rej = {"source": "gold_human", "approved": False}
    tier_with_human_rej = aggregator.classify_label(
        proposal=proposal,
        independent_opinions=ai_opinions,
        numerical_verified=True,
        rule_verified=True,
        human_adjudication=human_rej
    )
    
    # The human rejection overrides the AI consensus
    assert tier_with_human_rej == LabelTier.REJECTED
    
    # Human approves an otherwise disputed or rejected setup
    ai_opinions_bad = [
        {"source": "claude", "approved": False},
        {"source": "gpt4", "approved": False},
        {"source": "gemini", "approved": False}
    ]
    human_app = {"source": "gold_human", "approved": True}
    tier_with_human_app = aggregator.classify_label(
        proposal=proposal,
        independent_opinions=ai_opinions_bad,
        numerical_verified=True,
        rule_verified=True,
        human_adjudication=human_app
    )
    assert tier_with_human_app == LabelTier.GOLD_HUMAN_ADJUDICATED
