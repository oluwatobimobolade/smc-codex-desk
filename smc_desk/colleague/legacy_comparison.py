"""Legacy comparison adapter — the ONLY module allowed to import the old engine.

This adapter isolates the legacy analysis path. No current-authority module may
import smc_desk.engine.analyze_dataframe directly. When legacy comparison is
requested, the orchestrator calls run_legacy_comparison() which performs the
import and analysis inside this controlled boundary.

WP-0012A: All legacy analyzer calls must pass through this module.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from smc_desk.engine import analyze_dataframe, build_trade_plan_markdown
from smc_desk.mtf import build_mtf_snapshot, snapshot_to_dict
from smc_desk.rules import RuleConfig


def run_legacy_comparison(
    *,
    history_15m: pd.DataFrame,
    symbol: str,
    timeframe: str,
    decision_time: pd.Timestamp,
    config: RuleConfig,
    bias_hint: str | None = None,
) -> dict[str, Any]:
    """Run the legacy engine for comparison purposes only.

    This function is the SINGLE entry point for legacy analysis. No other module
    in the current-authority path may call analyze_dataframe().

    Returns a dict with legacy_analysis, legacy_df, trade_plan_md, and
    mtf_snapshot for the legacy comparison report.
    """
    from smc_desk.engine import analyze_dataframe as _legacy_adf
    from smc_desk.mtf import build_mtf_snapshot as _legacy_mtf, snapshot_to_dict as _mtf_to_dict

    mtf_model = _legacy_mtf(history_15m, decision_time, config)
    mtf_payload = _mtf_to_dict(mtf_model)

    legacy_analysis, legacy_df = _legacy_adf(
        df=history_15m,
        symbol=symbol,
        timeframe=timeframe,
        config=config,
        bias_hint=bias_hint,
        notes="legacy comparison for PerceptionEngineV2-led colleague package",
        input_type="ohlcv",
        htf_poi=mtf_model.selected_htf_poi,
    )

    legacy_payload = legacy_analysis.model_dump()
    trade_plan_md = build_trade_plan_markdown(legacy_analysis)

    return {
        "legacy_analysis": legacy_analysis,
        "legacy_df": legacy_df,
        "legacy_payload": legacy_payload,
        "trade_plan_md": trade_plan_md,
        "mtf_snapshot": mtf_payload,
    }


def run_legacy_annotation_analysis(
    *,
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    config: RuleConfig,
    notes: str,
) -> tuple[Any, pd.DataFrame]:
    """Run the old analyzer strictly for chart annotation provenance.

    WP-0020 still uses the legacy renderer's annotation vocabulary for visual
    audit charts. This adapter keeps that dependency inside the sanctioned
    legacy boundary so the gauntlet does not import the legacy engine directly.
    The returned analysis is not decision authority.
    """
    return analyze_dataframe(
        df=df,
        symbol=symbol,
        timeframe=timeframe,
        config=config,
        notes=notes,
    )
