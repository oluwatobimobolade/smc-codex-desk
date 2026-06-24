from typing import Dict, Any, List, Tuple
import pandas as pd
from smc_desk.knowledge.rule_cards import RuleCard
from smc_desk.teacher_panel.execution_record import AgentExecutionRecord

class AdversarialCritic:
    def __init__(self, prompt_version: str = "1.0.0", model_name: str = "default-adversarial-critic", temperature: float = 0.0):
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

    def critique_proposal(
        self,
        proposal: Dict[str, Any],
        df: pd.DataFrame,
        rule_card: RuleCard
    ) -> Tuple[Dict[str, Any], AgentExecutionRecord]:
        """
        Runs adversarial checks against the proposal to try to disprove it.
        """
        prompt = f"Critique {proposal.get('concept')} proposal."
        prompt_hash = AgentExecutionRecord.compute_hash(prompt)
        
        execution = AgentExecutionRecord(
            provider=self.provider,
            model_identifier=self.model_name,
            model_version=self.prompt_version,
            prompt_hash=prompt_hash,
            temperature=self.temperature,
            agent_role="AdversarialCritic"
        )
        
        disproved = False
        reasons = []
        
        concept = proposal.get("concept")
        if concept == "bos":
            # Check if it was only a wick break (high crossed, but close did not)
            idx = proposal.get("candle_index")
            level = proposal.get("price")
            candle = df.iloc[idx]
            
            # If close is below the break level, but high is above
            if candle["close"] < level and candle["high"] > level:
                disproved = True
                reasons.append("Wick break only: candle high crossed the level but close did not.")
                
        elif concept == "fvg":
            # Check if it was already fully mitigated immediately
            indices = proposal.get("candle_indices")
            if indices and len(indices) == 3:
                c3_idx = indices[2]
                fvg_low = proposal.get("price_low")
                fvg_high = proposal.get("price_high")
                # Look at subsequent candles to see if they mitigated
                for i in range(c3_idx + 1, min(c3_idx + 5, len(df))):
                    if df.iloc[i]["low"] <= fvg_low:
                        reasons.append(f"FVG fully mitigated by candle index {i} before proposal was finalized.")
                        
        return {
            "disproved": disproved,
            "reasons": reasons,
            "severity": "high" if disproved else "low"
        }, execution
