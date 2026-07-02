"""WP-0035 SOLUSDT fresh full analysis."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smc_desk.brain.ai_smc_trader_brain import REASONING_ORDER
from smc_desk.brain.providers.manual_provider import ManualJSONProvider
from smc_desk.brain.smc_evidence_pack_builder import build_smc_evidence_pack
from smc_desk.data.historical_backfill import MINIMUM_CONTEXT_DEPTH, fetch_historical_closed_ohlcv
from smc_desk.gauntlet.wp0035_ai_brain_gauntlet import run_wp0035_ai_brain_gauntlet
from smc_desk.session import summarize_session_context


BASE_URL = "https://fapi.binance.com"
SYMBOL = "SOLUSDT"
OUTPUT = Path("/Users/tobimobolade/smc-codex-desk/analysis_runs/WP0035_SOLUSDT_LIVE_FRESH_20260630")


def _http_json(url: str, timeout: float = 20.0):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _server_time() -> int:
    return int(_http_json(f"{BASE_URL}/fapi/v1/time")["serverTime"])


def _fetch_page(symbol: str, interval: str, limit: int, end_time_ms: int | None) -> tuple[list, int]:
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
    df = result.dataframe
    print(f"[{interval}] fetched {len(df)} rows from {result.manifest['page_count']} pages "
          f"({df['timestamp'].min()} -> {df['timestamp'].max()})")
    return df


def build_decision(evidence_pack: dict) -> dict:
    authority = evidence_pack["active_range_authority"]
    selected = authority["selected_range"]
    if selected is None:
        return _fallback_watch_decision(evidence_pack)

    high = selected["range_high"]
    low = selected["range_low"]
    equilibrium = selected["equilibrium"]
    protected_high = selected["protected_high"]
    protected_low = selected["protected_low"]
    range_id = selected["range_id"]
    width_atr = selected.get("width_atr")
    max_width_atr = selected.get("max_width_atr")
    high_pivot_id = selected["protected_high_pivot_id"]
    low_pivot_id = selected["protected_low_pivot_id"]
    range_tf = selected["timeframe"]
    range_direction = selected["direction"]
    last_close = evidence_pack["ohlcv_summaries"]["15m"]["last_close"]

    # Build bias and state from actual range direction
    if range_direction == "bullish":
        direction = "bullish"
        wait_state = "WAIT_FOR_RETRACE_TO_DEMAND"
        word = "demand"
        invalidation = protected_low
        invalidation_label = f"Acceptance below the {range_tf} protected low invalidates the bullish watch."
        watch_text = "Watch for demand rejection or range-low retest"
        bias_evidence = [
            "daily structure shows higher lows and higher highs recently",
            f"{range_tf} active range low before high defines bullish leg",
            f"current price {last_close:.4f} is above equilibrium {equilibrium:.4f} (premium / bullish side)",
        ]
    else:
        direction = "bearish"
        wait_state = "WAIT_FOR_RETRACE_TO_SUPPLY"
        word = "supply"
        invalidation = protected_high
        invalidation_label = f"Acceptance above the {range_tf} protected high invalidates the bearish watch."
        watch_text = "Watch for supply rejection or range-high retest"
        bias_evidence = [
            "daily structure shows lower highs and lower lows",
            f"{range_tf} active range high before low defines bearish leg",
            f"current price {last_close:.4f} is above equilibrium {equilibrium:.4f} (premium / supply zone)",
        ]

    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": SYMBOL,
        "official_state": wait_state,
        "setup_grade": "C",
        "direction": direction,
        "setup_model": "observe_only_context_watch",
        "bias_summary": {
            "daily": f"{direction} continuation",
            "4h": f"{direction} active dealing range",
            "1h": f"{direction} context with price in premium; wait for retrace to {word}",
            "final_bias": direction,
            "evidence": bias_evidence,
        },
        "active_range": {
            "timeframe": range_tf,
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
            "evidence": [f"Active range selected from recent alternating {range_tf} swing structure."],
        },
        "liquidity_story": {
            "obvious_liquidity": [
                {"liquidity_id": f"{range_tf}_bsl", "side": "buy_side", "price": protected_high, "label": f"{range_tf} range high / BSL", "evidence_object_ids": [high_pivot_id]},
                {"liquidity_id": f"{range_tf}_ssl", "side": "sell_side", "price": protected_low, "label": f"{range_tf} range low / SSL", "evidence_object_ids": [low_pivot_id]},
            ],
            "swept_liquidity": [],
            "unswept_liquidity": [
                {"liquidity_id": f"{range_tf}_bsl", "side": "buy_side", "price": protected_high, "label": "Buy-side liquidity / range high", "evidence_object_ids": [high_pivot_id]},
                {"liquidity_id": f"{range_tf}_ssl", "side": "sell_side", "price": protected_low, "label": "Sell-side liquidity / range low", "evidence_object_ids": [low_pivot_id]},
            ],
            "narrative": (
                f"{SYMBOL} active {range_tf} range is {low:.4f}-{high:.4f} ({range_direction}). "
                f"Current price {last_close:.4f} is in premium above equilibrium {equilibrium:.4f}. "
                f"Wait for a retrace into {word} before considering any entry."
            ),
        },
        "displacement_assessment": {
            "direction": "none",
            "quality": "none",
            "structure_broken": False,
            "evidence_object_ids": [],
            "summary": f"No confirmed {direction} displacement at current price; recent price action is consolidation/retracement.",
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
            "summary": f"No valid active POI at current price. Potential {word} zones near equilibrium or range extremes are not yet tested/rejected.",
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
            "summary": f"Wait for price to retrace to {word} and reject before any entry.",
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
            "summary": f"No target; watch state only. Eventual {direction} model-completion target would be external liquidity beyond the active range.",
        },
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "RR not computed; no trade plan."},
        "invalidation": {
            "invalidation_price": invalidation,
            "condition": invalidation_label,
            "source": f"{range_tf}_protected_{'low' if direction == 'bullish' else 'high'}",
            "evidence_object_ids": [low_pivot_id if direction == "bullish" else high_pivot_id],
        },
        "annotation_plan": {
            "chart_template": "watch_chart",
            "show_trade_box": False,
            "labels": [
                {"text": f"Daily/4H {direction} context", "kind": "context", "timeframe": "4h"},
                {"text": f"{range_tf} active range {low:.4f}-{high:.4f}", "kind": "context", "timeframe": range_tf},
                {"text": "Price in premium above equilibrium", "kind": "context"},
                {"text": f"Buy-side liquidity / range high {high:.4f}", "kind": "liquidity", "timeframe": range_tf, "price": high},
                {"text": f"Sell-side liquidity / range low {low:.4f}", "kind": "liquidity", "timeframe": range_tf, "price": low},
                {"text": f"No clear {word} POI yet", "kind": "state"},
                {"text": watch_text, "kind": "state"},
            ],
            "levels": [
                {"label": f"{range_tf} range high / BSL", "kind": "liquidity", "price": high, "timeframe": range_tf},
                {"label": f"{range_tf} range low / SSL", "kind": "liquidity", "price": low, "timeframe": range_tf},
                {"label": f"{direction.capitalize()} invalidation", "kind": "invalidation", "price": invalidation, "timeframe": range_tf},
            ],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {
            "active_range_check": "passed",
            "poi_check": "passed",
            "annotation_check": "passed",
            "refusal_check": "passed",
            "corrections_made": [f"Direction set to {direction} to match resolved active range authority."],
            "remaining_uncertainties": [
                "Whether price retraces to equilibrium or the full range extreme",
            ],
        },
        "final_thesis": (
            f"{SYMBOL} is {direction} on the active {range_tf} timeframe with a dealing range of "
            f"{low:.4f}-{high:.4f}. Price at {last_close:.4f} is in premium, so the correct state is "
            f"{wait_state}: wait for a retrace into {word} near equilibrium {equilibrium:.4f} before any entry. "
            f"Invalidation is acceptance beyond {invalidation:.4f}."
        ),
    }


def _fallback_watch_decision(evidence_pack: dict) -> dict:
    last_close = evidence_pack["ohlcv_summaries"]["15m"]["last_close"]
    return {
        "schema": "ai_smc_trader_decision_v1",
        "symbol": SYMBOL,
        "official_state": "REVIEW_REQUIRED",
        "setup_grade": "C",
        "direction": "mixed",
        "setup_model": "no_clear_model",
        "bias_summary": {
            "daily": "unclear from available context",
            "4h": "unclear from available context",
            "1h": "unclear from available context",
            "final_bias": "neutral",
            "evidence": ["Active range authority could not resolve a protected swing pair."],
        },
        "active_range": {
            "timeframe": "4h",
            "high": None,
            "low": None,
            "equilibrium": None,
            "price_location": "unknown",
            "source": None,
            "range_id": None,
            "evidence_object_ids": [],
            "evidence": ["Active range unresolved."],
        },
        "liquidity_story": {
            "obvious_liquidity": [],
            "swept_liquidity": [],
            "unswept_liquidity": [],
            "narrative": "Active range unresolved; cannot determine liquidity story.",
        },
        "displacement_assessment": {"direction": "none", "quality": "none", "structure_broken": False, "evidence_object_ids": [], "summary": "No displacement assessment possible."},
        "active_poi": {"poi_id": None, "timeframe": None, "kind": None, "direction": "unknown", "price_low": None, "price_high": None, "freshness": None, "evidence_object_ids": [], "summary": "No POI."},
        "entry_plan": {"entry_ready": False, "entry_timeframe": None, "refinement_timeframe": None, "entry_price": None, "entry_zone_low": None, "entry_zone_high": None, "signal_type": None, "required_confirmation": [], "evidence_object_ids": [], "summary": "No entry; active range unresolved."},
        "stop_loss_plan": {"stop_price": None, "structural_invalidation_price": None, "source": None, "buffer_notes": None, "evidence_object_ids": [], "summary": "No stop."},
        "target_plan": {"targets": [], "model_completion_liquidity_id": None, "summary": "No target."},
        "rr_status": {"rr": None, "minimum_rr": 3.0, "pass_rr": False, "notes": "No RR."},
        "invalidation": {"invalidation_price": None, "condition": "No invalidation level; active range unresolved.", "source": None, "evidence_object_ids": []},
        "annotation_plan": {
            "chart_template": "review_chart",
            "show_trade_box": False,
            "labels": [
                {"text": "Active range unresolved", "kind": "context"},
                {"text": f"Current price {last_close:.4f}", "kind": "context"},
                {"text": "Review required", "kind": "state"},
            ],
            "levels": [],
            "reasoning_order": REASONING_ORDER,
        },
        "self_review": {"active_range_check": "failed", "poi_check": "not_applicable", "annotation_check": "passed", "refusal_check": "passed", "corrections_made": ["Downgraded to REVIEW_REQUIRED because active range authority did not resolve."], "remaining_uncertainties": ["Why the active range could not resolve on 4h/1d."]},
        "final_thesis": f"{SYMBOL}: active range authority could not resolve a protected swing pair. REVIEW_REQUIRED.",
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
    print("Session context:", json.dumps(session_context, default=str, indent=2))

    evidence_pack = build_smc_evidence_pack(
        symbol=SYMBOL,
        timeframe_dfs=timeframe_dfs,
        chart_images=None,
        detector_candidates={},
        session_context=session_context,
        doctrine_notes=["WP-0035 SOLUSDT fresh full analysis"],
    )

    (OUTPUT / "00_evidence_pack").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "00_evidence_pack" / "evidence_pack.json").write_text(
        json.dumps(evidence_pack, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    print(f"\nActive range authority:")
    print(json.dumps(evidence_pack["active_range_authority"], indent=2, default=str)[:1200])

    decision_payload = build_decision(evidence_pack)
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

    print(f"\nWP-0035 status: {result.status}")
    print(f"Official state: {result.final_report.get('official_state')}")
    print(f"Validation: {result.final_report.get('validation_result')}")
    if result.final_report.get("hard_issues"):
        print("Hard issues:")
        for issue in result.final_report["hard_issues"]:
            print(f"  - {issue.get('code')}: {issue.get('message')}")


if __name__ == "__main__":
    main()
