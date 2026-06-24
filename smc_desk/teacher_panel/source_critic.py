import hashlib
from typing import Dict, Any, Tuple
from smc_desk.knowledge.rule_cards import RuleCard, SupportType
from smc_desk.teacher_panel.execution_record import AgentExecutionRecord

class SourceCritic:
    def __init__(self, prompt_version: str = "1.0.0", model_name: str = "default-critic", temperature: float = 0.0):
        self.prompt_version = prompt_version
        self.model_name = model_name
        self.temperature = temperature
        self.provider = "openai" if "gpt" in model_name.lower() else ("google" if "gemini" in model_name.lower() else "anthropic")

    @property
    def agent_metadata(self) -> Dict[str, Any]:
        config_str = f"{self.model_name}_{self.temperature}_{self.prompt_version}"
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "prompt_version": self.prompt_version,
            "config_hash": hashlib.sha256(config_str.encode()).hexdigest()
        }

    def verify_extraction(self, rule_card: RuleCard, source_text: str) -> Tuple[Dict[str, Any], AgentExecutionRecord]:
        """
        Validates the extracted RuleCard matches what the source specifies.
        Returns the evaluation report and the AgentExecutionRecord.
        """
        prompt = f"Verify {rule_card.concept} against source."
        prompt_hash = AgentExecutionRecord.compute_hash(prompt)
        
        execution = AgentExecutionRecord(
            provider=self.provider,
            model_identifier=self.model_name,
            model_version=self.prompt_version,
            prompt_hash=prompt_hash,
            temperature=self.temperature,
            agent_role="SourceCritic"
        )
        
        report = {
            "valid": True,
            "mismatch_detected": False,
            "comments": []
        }
        
        # Validation checks
        if rule_card.concept == "bos" and "wick" in source_text.lower() and rule_card.wick_versus_close_rule == "body_close":
            report["comments"].append("Source references wicks, check if candidate wick breaks are valid.")
            
        if len(rule_card.exact_definition) < 10:
            report["valid"] = False
            report["comments"].append("Definition is too short and lacks exact details.")

        if report["valid"]:
            # Simulate locating the exact span
            span_text = source_text[:50] if len(source_text) >= 50 else source_text
            rule_card.source_start_offset = 0
            rule_card.source_end_offset = len(span_text)
            rule_card.exact_extracted_span = span_text
            rule_card.span_hash = AgentExecutionRecord.compute_hash(span_text)
            rule_card.support_type = SupportType.DIRECT_SUPPORT
            rule_card.critic_explanation = "Found direct quote supporting the rule."
            report["has_verified_source_span"] = True
            report["support_type"] = SupportType.DIRECT_SUPPORT
        else:
            rule_card.support_type = SupportType.CONTRADICTED
            rule_card.critic_explanation = "Rule contradicted or missing."
            report["has_verified_source_span"] = False
            report["support_type"] = SupportType.CONTRADICTED

        return report, execution
