from typing import List, Dict, Any, Tuple
import pandas as pd
from smc_desk.knowledge.rule_cards import RuleCard
from smc_desk.teacher_panel.execution_record import AgentExecutionRecord

class ChartAnnotator:
    def __init__(self, prompt_version: str = "1.0.0", model_name: str = "default-annotator", temperature: float = 0.0):
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

    def generate_candidate_annotations(
        self,
        df: pd.DataFrame,
        rule_card: RuleCard
    ) -> Tuple[List[Dict[str, Any]], AgentExecutionRecord]:
        """
        Scans candle data and proposes visual annotations matching the rule card.
        """
        prompt = f"Annotate {rule_card.concept}."
        prompt_hash = AgentExecutionRecord.compute_hash(prompt)
        
        execution = AgentExecutionRecord(
            provider=self.provider,
            model_identifier=self.model_name,
            model_version=self.prompt_version,
            prompt_hash=prompt_hash,
            temperature=self.temperature,
            agent_role="ChartAnnotator"
        )
        
        proposals = []
        concept = rule_card.concept.lower()
        
        # Propose annotations based on the rule card definition
        if concept == "fvg":
            # Simple FVG scanning proposal
            for i in range(2, len(df)):
                c1_hi = df.iloc[i-2]["high"]
                c3_lo = df.iloc[i]["low"]
                if c1_hi < c3_lo:
                    proposals.append({
                        "proposal_id": f"prop_fvg_{i}",
                        "source_rule_id": rule_card.rule_id,
                        "concept": "fvg",
                        "direction": "bullish",
                        "price_low": float(c1_hi),
                        "price_high": float(c3_lo),
                        "candle_indices": (i-2, i-1, i),
                        "confidence": 0.95
                    })
        elif concept == "bos":
            # Simple BOS scanning proposal
            # Propose when close is higher than recent highs
            for i in range(5, len(df)):
                recent_max = df.iloc[i-5:i]["high"].max()
                if df.iloc[i]["close"] > recent_max:
                    proposals.append({
                        "proposal_id": f"prop_bos_{i}",
                        "source_rule_id": rule_card.rule_id,
                        "concept": "bos",
                        "direction": "bullish",
                        "price": float(recent_max),
                        "candle_index": i,
                        "confidence": 0.8
                    })
        return proposals, execution
