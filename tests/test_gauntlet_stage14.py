import pytest
from smc_desk.knowledge.rule_cards import RuleCard
from smc_desk.knowledge.ingestion_pipeline import IngestionPipeline

def test_adversarial_ingestion():
    """Stage 14: Adversarial Ingestion Test
    Feed the system an adversarial or entirely fake 'trading guru' rulebook.
    Verify that the system isolates this knowledge into a distinct RuleCard
    with its own ID, and does not pollute the standard SMC definitions.
    """
    pipeline = IngestionPipeline()
    
    # Fake guru document
    adversarial_doc = """
    Welcome to FakeGuru SMC.
    In my academy, a Bullish Break of Structure (BOS) is defined as:
    When a RED candle closes below a previous GREEN candle's low.
    Yes, you read that right.
    """
    
    # Ingest the adversarial doc
    fake_cards = pipeline.extract_rules(adversarial_doc, source_name="FakeGuru_Course")
    
    # Check that a rule card was extracted
    assert len(fake_cards) > 0
    fake_bos_card = fake_cards[0]
    
    # It must have a unique rule ID
    assert fake_bos_card.rule_id is not None
    assert fake_bos_card.academy == "FakeGuru_Course"
    
    # It must capture the exact definition without "correcting" it to standard SMC
    assert "red" in fake_bos_card.exact_definition.lower()
    assert "below" in fake_bos_card.exact_definition.lower()
    
    # The standard SMC rules must remain unaffected
    standard_bos_card = pipeline.get_standard_rule("BOS")
    if standard_bos_card:
        assert standard_bos_card.rule_id != fake_bos_card.rule_id
        assert "red" not in standard_bos_card.exact_definition.lower()

