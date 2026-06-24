from typing import Dict, Any, Tuple
import pandas as pd
from smc_desk.synthetic.counterfactuals import CounterfactualGenerator

class CounterfactualTestRunner:
    def __init__(self):
        self.generator = CounterfactualGenerator()

    def run_structure_break_counterfactual_test(
        self,
        df: pd.DataFrame,
        level: float,
        break_candle_idx: int,
        detect_func: Any,  # detect_structure_events or similar function
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Runs counterfactual tests:
        1. Modifies candle to be a wick-only probe -> expects no body-close break (candidate/wick break).
        2. Modifies candle to be a body-close break -> expects confirmed break.
        """
        # Test Case 1: Wick probe
        df_wick, _ = self.generator.create_wick_probe_counterfactual(df, level, break_candle_idx)
        events_wick = detect_func(df_wick, config)
        
        # Test Case 2: Body close break
        df_body, _ = self.generator.create_body_close_break_counterfactual(df, level, break_candle_idx)
        events_body = detect_func(df_body, config)
        
        # Check if the body close version contains a confirmed BOS/CHoCH,
        # whereas the wick close version does not (it is a candidate/wick break only).
        confirmed_body = any(e.get("confirmed", False) for e in events_body)
        confirmed_wick = any(e.get("confirmed", False) for e in events_wick)
        
        return {
            "success": confirmed_body == True and confirmed_wick == False,
            "confirmed_body": confirmed_body,
            "confirmed_wick": confirmed_wick
        }
