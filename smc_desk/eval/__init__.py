"""Evaluation helpers for AI SMC brain work packages."""

from smc_desk.eval.ai_smc_gold_evaluator import compare_ai_output_to_human_labels
from smc_desk.eval.gold_set_loader import GoldChartCase, load_gold_chart_cases

__all__ = ["GoldChartCase", "compare_ai_output_to_human_labels", "load_gold_chart_cases"]
