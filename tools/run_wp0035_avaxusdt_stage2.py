"""Stage 2: run WP-0035 AVAXUSDT with manual AI decision."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER
from smc_desk.brain.providers.manual_provider import ManualJSONProvider
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.data.historical_backfill import MINIMUM_CONTEXT_DEPTH, fetch_historical_closed_ohlcv
from smc_desk.gauntlet.wp0035_ai_brain_gauntlet import run_wp0035_ai_brain_gauntlet
from smc_desk.session import summarize_session_context


BASE_URL = "https://fapi.binance.com"
SYMBOL = "AVAXUSDT"
OUTPUT = Path("/Users/tobimobolade/smc-codex-desk/analysis_runs/WP0035_AVAXUSDT_LIVE_20260629")


def _http_json(url: str, timeout: float = 20.0):
    import requests

    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _server_time() -> int:
    return int(_http_json(f"{BASE_URL}/fapi/v1/time")["serverTime"])


def _fetch_page(symbol: str, interval: str, limit: int, end_time_ms: int | None) -> tuple[list, int]:
    from urllib.parse import urlencode
    import time

    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if end_time_ms is not None:
        params["endTime"] = int(end_time_ms)
    url = f"{BASE_URL}/fapi/v1/klines?{urlencode(params)}"
    time.sleep(0.25)
    rows = _http_json(url)
    server_time = _server_time()
    return rows, server_time


def fetch_tf(interval: str, required: int | None = None) -> pd.DataFrame:
    result = fetch_historical_closed_ohlcv(
        symbol=SYMBOL,
        interval=interval,
        required_candles=required or MINIMUM_CONTEXT_DEPTH.get(interval, 1500),
        fetcher=_fetch_page,
        cache_dir=OUTPUT / "data" / interval,
    )
    return result.dataframe


def build_decision(evidence_pack: dict) -> dict:
    authority = evidence_pack["active_range_authority"]
    selected = authority["selected_range"]
    high = selected["range_high"]
    low = selected["range_low"]
    equilibrium = selected["equilibrium"]
    protected_high = selected["protected_high"]
    protected_low = selected["protected_low"]
    range_id = selected["range_id"]
    width_atr = selected["width_atr"]
    max_width_atr = selected["max_width_atr"]
    high_pivot_id = selected["protected_high_pivot_id"]
    low_pivot_id = selected["protected_low_pivot_id"]

    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": SYMBOL,
        "official_state": "WATCH_ONLY",
        "setup_grade": "C",
        "direction": "bearish",
        "setup_model": "observe_only_context_watch",
        "bias_summary": {
            "daily": "bearish corrective structure within broader downtrend",
            "4h": "bearish active dealing range; price in premium",
            "1h": "bearish context with internal bullish retracement; not authority",
            "final_bias": "bearish",
            "evidence": [
                "daily structure remains bearish from 36.16 high",
                "4h active range high 7.018 before low 5.673 defines bearish leg",
                "current price 6.741 is above equilibrium 6.345 (premium)",
                "1h higher lows are internal retracement, not external reversal",
            ],
        },
        "active_range": {
            "timeframe": "4h",
            "high": high,
            "low": low,
            "equilibrium": equilibrium,
            "price_location": "premium",
            "source": "protected_swing_pair",
            "range_id": range_id,
            "protected_high": protected_high,
            "protected_low": protected_low,
            "width_atr": width_atr,
            "max_allowed_width_atr": max_width_atr,
            "evidence_object_ids": [high_pivot_id, low_pivot_id],
            "evidence": ["Active range selected from recent alternating 4h swing structure."],
        },
        "liquidity_story": {
            "obvious_liquidity": [
                {"liquidity_id": "4h_bsl", "side": "buy_side", "price": protected_high, "label": "4h range high / external buy-side liquidity", "evidence_object_ids": [high_pivot_id]},
                {"liquidity_id": "4h_ssl", "side": "sell_side", "price": protected_low, "label": "4h range low / external sell-side liquidity", "evidence_object_ids": [low_pivot_id]},
            ],
            "swept_liquidity": [],
            "unswept_liquidity": [
                {"liquidity_id": "4h_bsl", "side": "buy_side", "price": protected_high, "label": "4h range high / external buy-side liquidity", "evidence_object_ids": [high_pivot_id]},
                {"liquidity_id": "4h_ssl", "side": "sell_side", "price": protected_low, "label": "4h range low / external sell-side liquidity", "evidence_object_ids": [low_pivot_id]},
            ],
            "narrative": (
                "AVAX is in a bearish 4h dealing range after sweeping the 5.673 low on June 19. "
                "Price has retraced into premium (6.741 vs equilibrium 6.345). "
                "The logical model-completion draw for any bearish continuation is the external sell-side liquidity at 5.673. "
                "Buy-side liquidity rests above the range high at 7.018. "
                "No clean POI or displacement has confirmed at the current price; watch only."
            ),
        },
        "displacement_assessment": {
            "direction": "none",
            "quality": "none",
            "structure_broken": False,
            "evidence_object_ids": [],
            "summary": (
                "Recent 15m/1h up-move from 6.443 to 6.818 is internal retracement into premium, "
                "not a HTF structural shift. No confirmed bearish displacement toward 5.673 yet."
            ),
        },
        "active_poi": {
            "poi_id": None,
            "timeframe": None,
            "kind": None,
            "direction": "unknown",
            "price_low": None,
            "price_high": None,
            "freshness": None,
            "evidence_object_ids": [],
            "summary": "No valid active POI at current price. Potential supply zones near 6.80-7.018 are not yet tested/rejected.",
        },
        "entry_plan": {
            "entry_ready": False,
            "entry_timeframe": None,
            "refinement_timeframe": None,
            "entry_price": None,
            "entry_zone_low": None,
            "entry_zone_high": None,
            "signal_type": None,
            "required_confirmation": [],
            "evidence_object_ids": [],
            "summary": "No entry. Watch for price to reach a valid supply zone (near 7.018 range high or a fresh 15m supply) and reject with displacement.",
        },
        "stop_loss_plan": {
            "stop_price": None,
            "structural_invalidation_price": None,
            "source": None,
            "buffer_notes": None,
            "evidence_object_ids": [],
            "summary": "No stop; watch state only.",
        },
        "target_plan": {
            "targets": [],
            "model_completion_liquidity_id": None,
            "summary": "No target; watch state only. Eventual bearish model-completion target would be external sell-side liquidity at 5.673 if a valid short develops.",
        },
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "RR not computed; no trade plan."},
        "invalidation": {
            "invalidation_price": protected_high,
            "condition": "Acceptance above the 4h protected high / range high invalidates the bearish watch and requires a remap.",
            "source": "4h_protected_high",
            "evidence_object_ids": [high_pivot_id],
        },
        "annotation_plan": {
            "chart_template": "watch_chart",
            "show_trade_box": False,
            "labels": [
                {"text": "Daily/4H bearish context", "kind": "context", "timeframe": "4h"},
                {"text": f"4h active range {low:.3f}-{high:.3f}", "kind": "context", "timeframe": "4h"},
                {"text": "Price in premium above equilibrium", "kind": "context"},
                {"text": f"Buy-side liquidity / range high {high:.3f}", "kind": "liquidity", "timeframe": "4h", "price": high},
                {"text": f"Sell-side liquidity / range low {low:.3f}", "kind": "liquidity", "timeframe": "4h", "price": low},
                {"text": "No clear POI or displacement yet", "kind": "state"},
                {"text": "Watch for supply rejection or range-high sweep", "kind": "state"},
            ],
            "levels": [
                {"label": "4h range high / BSL", "kind": "liquidity", "price": high, "timeframe": "4h"},
                {"label": "4h range low / SSL", "kind": "liquidity", "price": low, "timeframe": "4h"},
                {"label": "Bearish invalidation", "kind": "invalidation", "price": protected_high, "timeframe": "4h"},
            ],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "passed",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": ["Removed attempted supply zone at 6.80 because it lacks visible rejection or displacement evidence."],
            "remaining_uncertainties": [
                "Whether the 6.818 internal high was a liquidity sweep or genuine breakout",
                "Whether price will reach the 7.018 range high before reversing",
            ],
        },
        "final_thesis": (
            "AVAXUSDT is bearish on daily and 4h timeframes, trading in premium of a 4h dealing range "
            f"({low:.3f}-{high:.3f}). The model-completion draw for bearish continuation is the external "
            f"sell-side liquidity at {low:.3f}, but no valid POI or displacement has formed at the current "
            f"price ({evidence_pack['ohlcv_summaries']['15m']['last_close']:.3f}). Watch only; wait for "
            f"price to reach supply near {high:.3f} and reject, or for bearish displacement to break recent "
            "internal structure. Acceptance above 7.018 invalidates the bearish watch."
        ),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    timeframe_dfs = {
        "15m": fetch_tf("15m"),
        "1h": fetch_tf("1h"),
        "4h": fetch_tf("4h"),
        "1d": fetch_tf("1d"),
    }

    session_context = summarize_session_context(timeframe_dfs["15m"])
    evidence_pack = build_smc_evidence_pack(
        symbol=SYMBOL,
        timeframe_dfs=timeframe_dfs,
        chart_images=None,
        detector_candidates={},
        session_context=session_context,
        doctrine_notes=["WP-0035 AVAXUSDT live analysis"],
    )

    decision_payload = build_decision(evidence_pack)

    # Write the manual AI decision for audit
    (OUTPUT / "00_manual_ai_decision").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "00_manual_ai_decision" / "ai_decision.json").write_text(
        json.dumps(decision_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    provider = ManualJSONProvider(
        decision_payload,
        provider_name="opencode_manual_ai_reasoning",
        model_name="kimi-k2.7-code",
        is_real_reasoning=True,
    )

    result = run_wp0035_ai_brain_gauntlet(
        symbol=SYMBOL,
        timeframe_dfs=timeframe_dfs,
        provider=provider,
        output_dir=OUTPUT / "wp0035_run",
        detector_candidates={},
        enforce_minimum_depth=True,
    )

    print(f"WP-0035 status: {result.status}")
    print(f"Output: {result.output_dir}")
    print(f"Official state: {result.final_report.get('official_state')}")
    print(f"Validation: {result.final_report.get('validation_result')}")
    print(f"Provider stub warning: {result.final_report.get('stub_provider_warning')}")
    if result.final_report.get("hard_issues"):
        print("Hard issues:")
        for issue in result.final_report["hard_issues"]:
            print(f"  - {issue.get('code')}: {issue.get('message')}")


if __name__ == "__main__":
    main()
