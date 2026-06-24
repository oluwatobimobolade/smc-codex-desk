from typing import Dict, Any, List, Tuple
import pandas as pd
from smc_desk.teacher_panel.execution_record import AgentExecutionRecord

class IndependentJudge:
    def __init__(self, prompt_version: str = "1.0.0", model_name: str = "default-judge", temperature: float = 0.0):
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

    def adjudicate(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        numerical_valid: bool,
        is_unresolved: bool = False
    ) -> Tuple[Dict[str, Any], AgentExecutionRecord]:
        """
        Adjudicates between proposal, critique, and numerical evidence to make the final decision.
        """
        prompt = f"Adjudicate {proposal.get('concept')}."
        prompt_hash = AgentExecutionRecord.compute_hash(prompt)
        
        execution = AgentExecutionRecord(
            provider=self.provider,
            model_identifier=self.model_name,
            model_version=self.prompt_version,
            prompt_hash=prompt_hash,
            temperature=self.temperature,
            agent_role="IndependentJudge"
        )
        
        if is_unresolved:
            return {
                "proposal_id": proposal.get("proposal_id"),
                "approved": False,
                "is_unresolved": True,
                "decision_reason": "Judge could not confidently resolve.",
                "final_confidence": 0.0
            }, execution
        
        # A proposal must be numerically valid AND not disproved by the adversarial critic
        disproved = critique.get("disproved", False)
        
        approved = numerical_valid and not disproved
        decision_reason = "Numerical validation passed and adversarial critique found no flaws."
        
        if not numerical_valid:
            decision_reason = "Failed absolute numerical validation check."
        elif disproved:
            decision_reason = f"Adversarial critic disproved the proposal: {', '.join(critique.get('reasons', []))}"
            
        return {
            "proposal_id": proposal.get("proposal_id"),
            "approved": approved,
            "is_unresolved": False,
            "decision_reason": decision_reason,
            "final_confidence": proposal.get("confidence", 0.5) if approved else 0.0
        }, execution
