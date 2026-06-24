import pytest
from smc_desk.teacher_panel.weak_label_aggregator import WeakLabelAggregator, LabelTier

def test_false_consensus_trap():
    """Stage 9: False-Consensus Trap Test
    If multiple LLMs hallucinate the same structure due to training data overlap,
    and all agree it is valid, the label must still be capped below high-confidence
    if the deterministic numerical check fails.
    """
    aggregator = WeakLabelAggregator()

    proposal = {"kind": "bos", "price": 100.5}

    # 3 independent AI models all agree due to hallucination/overlap
    opinions = [
        {"model": "gpt-4", "approved": True},
        {"model": "claude-3", "approved": True},
        {"model": "gemini-pro", "approved": True}
    ]

    # The deterministic truth layer (numerical_verified) says False.
    # The models hallucinated the BOS.
    numerical_verified = False
    rule_verified = True # They followed the rule instructions, but math failed

    tier = aggregator.classify_label(
        proposal=proposal,
        independent_opinions=opinions,
        numerical_verified=numerical_verified,
        rule_verified=rule_verified
    )

    # Must NOT reach GOLD or SILVER_HIGH_CONFIDENCE
    assert tier == LabelTier.SILVER_AI_CONSENSUS
    assert tier != LabelTier.SILVER_HIGH_CONFIDENCE
    assert tier != LabelTier.GOLD_OBJECTIVE_ORACLE
    assert tier != LabelTier.GOLD_HUMAN_ADJUDICATED

def test_false_consensus_trap_disputed():
    """If there is partial consensus but numericals fail, it stays disputed or bronze."""
    aggregator = WeakLabelAggregator()
    opinions = [
        {"model": "gpt-4", "approved": True},
        {"model": "claude-3", "approved": True},
        {"model": "gemini-pro", "approved": False}
    ]

    tier = aggregator.classify_label(
        proposal={},
        independent_opinions=opinions,
        numerical_verified=False,
        rule_verified=True
    )
    
    assert tier == LabelTier.DISPUTED

