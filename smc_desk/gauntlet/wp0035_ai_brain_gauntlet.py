"""WP-0035 AI brain integration gauntlet."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from smc_desk.brain.llm_provider import AISMCProvider
from smc_desk.colleague.orchestrator_v3 import run_ai_smc_orchestrator_v3


WP0035_STAGES = (
    "09_clean_mtf_chart_pack",
    "10_smc_evidence_pack",
    "11_ai_smc_trader_brain",
    "12_ai_consistency_validation",
    "13_official_ai_decision",
    "14_clean_annotation_render",
    "15_ai_thesis",
    "16_tradingview_visual_check_optional",
)


@dataclass(frozen=True)
class WP0035GauntletResult:
    output_dir: Path
    status: str
    final_report: dict[str, Any]


def run_wp0035_ai_brain_gauntlet(
    *,
    symbol: str,
    timeframe_dfs: Mapping[str, pd.DataFrame],
    provider: AISMCProvider,
    output_dir: str | Path,
    detector_candidates: Mapping[str, Any] | None = None,
    enforce_minimum_depth: bool = True,
    capture_tradingview: bool = False,
) -> WP0035GauntletResult:
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = run_ai_smc_orchestrator_v3(
        symbol=symbol,
        timeframe_dfs=timeframe_dfs,
        provider=provider,
        output_dir=root,
        detector_candidates=detector_candidates,
        enforce_minimum_depth=enforce_minimum_depth,
    )
    final = dict(result.report)
    final["wp0035_stages"] = list(WP0035_STAGES)
    final["tradingview_visual_check"] = (
        _capture_tradingview_screenshot(symbol, root / "16_tradingview_visual_check")
        if capture_tradingview
        else {"status": "SKIPPED", "reason": "capture_tradingview=false"}
    )
    final["stub_provider_warning"] = (
        "NOT_REAL_AI_REASONING - STUB_PROVIDER"
        if result.provider_result.is_stub or not result.provider_result.is_real_reasoning
        else None
    )
    (root / "wp0035_gauntlet_report.json").write_text(json.dumps(final, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return WP0035GauntletResult(output_dir=root, status=result.status, final_report=final)


def _capture_tradingview_screenshot(symbol: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tv_symbol = _tradingview_symbol(symbol)
    output_path = output_dir / f"{symbol}_tradingview_screenshot.png"
    url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
    try:
        from smc_desk.vision.kimi_webbridge import KimiWebBridge

        screenshot_bytes = KimiWebBridge(headless=True).capture_chart(url)
        output_path.write_bytes(screenshot_bytes)
        return {
            "status": "CAPTURED" if output_path.exists() else "FAILED",
            "url": url,
            "tradingview_symbol": tv_symbol,
            "path": str(output_path),
        }
    except Exception as exc:
        return {
            "status": "SKIPPED",
            "url": url,
            "tradingview_symbol": tv_symbol,
            "reason": str(exc),
            "error_type": type(exc).__name__,
        }


def _tradingview_symbol(symbol: str) -> str:
    upper = symbol.upper().replace("/", "").replace("-", "")
    if ":" in symbol:
        return symbol
    if upper.endswith("USDT"):
        return f"BINANCE:{upper}.P"
    if upper == "XAUUSD":
        return "OANDA:XAUUSD"
    currencies = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"}
    if len(upper) == 6 and upper[:3] in currencies and upper[3:] in currencies:
        return f"OANDA:{upper}"
    return upper
