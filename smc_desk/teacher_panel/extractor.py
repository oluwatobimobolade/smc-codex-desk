import json
import re
import unicodedata
from typing import Dict, Any, Optional, Tuple
from smc_desk.knowledge.rule_cards import RuleCard
from smc_desk.teacher_panel.execution_record import AgentExecutionRecord

class RuleExtractor:
    def __init__(self, prompt_version: str = "1.0.0", model_name: str = "default-extractor", temperature: float = 0.0):
        self.prompt_version = prompt_version
        self.model_name = model_name
        self.temperature = temperature
        self.provider = "openai" if "gpt" in model_name.lower() else ("google" if "gemini" in model_name.lower() else "anthropic")

    @property
    def agent_metadata(self) -> Dict[str, Any]:
        import hashlib
        config_str = f"{self.model_name}_{self.temperature}_{self.prompt_version}"
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "prompt_version": self.prompt_version,
            "config_hash": hashlib.sha256(config_str.encode()).hexdigest()
        }

    def sanitize_input(self, text: str) -> str:
        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)
        # Remove control characters except tab, newline, return
        text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\t", "\n", "\r"))
        
        # Strip basic HTML tags
        sanitized = re.sub(r'<[^>]*>', '', text)
        # Check for common injection phrases
        injection_keywords = ["ignore previous instructions", "system:", "you are now"]
        for kw in injection_keywords:
            if kw.lower() in sanitized.lower():
                raise ValueError("Potential prompt injection detected.")
        return sanitized

    def extract_rule_card(self, source_text: str, concept: str, academy: str) -> Tuple[RuleCard, AgentExecutionRecord]:
        """
        Extracts structured RuleCard from transcript or source text.
        In dry-run or mock execution, parses structured content.
        """
        # Sanitize input first
        sanitized_text = self.sanitize_input(source_text)
        
        # Format the prompt using strongly delimited container
        prompt = f"Extract rules for {concept}. Source:\n<UNTRUSTED_SOURCE>\n{sanitized_text}\n</UNTRUSTED_SOURCE>"
        prompt_hash = AgentExecutionRecord.compute_hash(prompt)
        
        execution = AgentExecutionRecord(
            provider=self.provider,
            model_identifier=self.model_name,
            model_version=self.prompt_version,
            prompt_hash=prompt_hash,
            temperature=self.temperature,
            agent_role="RuleExtractor"
        )
        
        # Simulates extraction parser guided by prompts
        if "BOS" in source_text or "bos" in source_text:
            return RuleCard(
                concept=concept,
                academy=academy,
                exact_definition="Price breaks structure by body close",
                required_conditions=["body close confirmation", "established swing high/low"],
                wick_versus_close_rule="body_close",
                confidence_in_extraction=0.9,
                source_references=["src_001"]
            ), execution
        elif "FVG" in source_text or "fvg" in source_text:
            return RuleCard(
                concept=concept,
                academy=academy,
                exact_definition="Gap between c1 high and c3 low",
                required_conditions=["lack of overlap"],
                wick_versus_close_rule="either",
                confidence_in_extraction=0.95,
                source_references=["src_002"]
            ), execution
        else:
            return RuleCard(
                concept=concept,
                academy=academy,
                exact_definition=source_text[:100],
                wick_versus_close_rule="either",
                confidence_in_extraction=0.5
            ), execution
