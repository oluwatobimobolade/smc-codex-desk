from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .engine import analyze_dataframe
from .mtf import build_mtf_snapshot, derive_htf_consensus_bias, precompute_htf_series, snapshot_to_dict
from .rules import RuleConfig


CASE_VERSION = "1.0"
NO_LEAKAGE_RULE = "15m history is sliced to timestamp <= decision_time; HTF candles are visible only when close_time <= decision_time."


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_ohlcv_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True).dt.tz_convert(None)
    return normalized.sort_values("timestamp").reset_index(drop=True)


def parse_decision_time(value: str | None, df: pd.DataFrame) -> pd.Timestamp:
    if value:
        parsed = pd.to_datetime(value, utc=True)
        return pd.Timestamp(parsed).tz_convert(None)
    return pd.Timestamp(df["timestamp"].iloc[-1])


def data_quality_report(df: pd.DataFrame, expected_step_minutes: int = 15) -> dict[str, Any]:
    if df.empty:
        return {
            "rows": 0,
            "start": None,
            "end": None,
            "expected_step_minutes": expected_step_minutes,
            "duplicate_timestamps": 0,
            "out_of_order_rows": 0,
            "gap_count": 0,
            "max_gap_minutes": None,
            "nan_ohlc_rows": 0,
            "zero_or_negative_volume_rows": 0,
        }

    timestamps = pd.to_datetime(df["timestamp"], utc=False)
    deltas = timestamps.diff().dropna()
    expected_delta = pd.Timedelta(minutes=expected_step_minutes)
    gaps = deltas[deltas != expected_delta]
    volume = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    return {
        "rows": int(len(df)),
        "start": pd.Timestamp(timestamps.iloc[0]).isoformat(),
        "end": pd.Timestamp(timestamps.iloc[-1]).isoformat(),
        "expected_step_minutes": expected_step_minutes,
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "out_of_order_rows": int((timestamps.diff().dropna() < pd.Timedelta(0)).sum()),
        "gap_count": int(len(gaps)),
        "max_gap_minutes": round(float(gaps.max() / pd.Timedelta(minutes=1)), 4) if not gaps.empty else None,
        "nan_ohlc_rows": int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "zero_or_negative_volume_rows": int((volume <= 0).sum()),
    }


def load_screenshot_metadata(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    screenshots = payload.get("screenshots", {})

    def resolve_screenshot(value: Any) -> str:
        screenshot_path = Path(str(value))
        if screenshot_path.is_absolute():
            return str(screenshot_path)
        cwd_path = (Path.cwd() / screenshot_path).resolve()
        if cwd_path.exists():
            return str(cwd_path)
        return str((path.parent / screenshot_path).resolve())

    return {
        "metadata_path": str(path.resolve()),
        "instrument": payload.get("instrument"),
        "exchange": payload.get("exchange"),
        "tradingview_symbol": payload.get("tradingview_symbol"),
        "captured_at": payload.get("captured_at"),
        "urls": payload.get("urls", {}),
        "screenshots": {key: resolve_screenshot(value) for key, value in screenshots.items()},
    }


def expert_label_scaffold() -> dict[str, Any]:
    return {
        "review_status": "unreviewed",
        "expert_name_or_source": None,
        "expert_bias": None,
        "expert_htf_narrative": None,
        "expert_dealing_range": None,
        "expert_liquidity_swept": None,
        "expert_poi_quality": None,
        "expert_confirmation_quality": None,
        "expert_grade": None,
        "expert_verdict": None,
        "expert_entry_model": None,
        "expert_invalidation": None,
        "expert_structural_invalidation": None,
        "expert_execution_stop": None,
        "expert_targets": [],
        "trade_taken": None,
        "outcome_r": None,
        "mistake_tags": [],
        "correction_notes": None,
    }


def _chart_source_matches(exchange: str | None, screenshot_meta: dict[str, Any] | None) -> bool | None:
    if not screenshot_meta:
        return None
    tradingview_symbol = str(screenshot_meta.get("tradingview_symbol") or "")
    if not tradingview_symbol:
        return None
    if not exchange:
        return None
    return tradingview_symbol.upper().startswith(f"{exchange.upper()}:")


def build_case_payload(
    *,
    symbol: str,
    exchange: str | None,
    ohlcv_path: Path,
    df: pd.DataFrame,
    config: RuleConfig,
    decision_time: str | None = None,
    screenshot_meta: dict[str, Any] | None = None,
    notes: str | None = None,
    case_kind: str = "live_analysis",
    data_source_name: str = "OHLCV source",
    expected_step_minutes: int = 15,
) -> dict[str, Any]:
    normalized_df = normalize_ohlcv_timestamps(df)
    if normalized_df.empty:
        raise ValueError("OHLCV dataframe is empty.")

    decision_ts = parse_decision_time(decision_time, normalized_df)
    visible_df = normalized_df.loc[normalized_df["timestamp"] <= decision_ts].reset_index(drop=True)
    if visible_df.empty:
        raise ValueError("No candles are visible at the requested decision time.")
    last_visible = pd.Timestamp(visible_df["timestamp"].iloc[-1])

    precomputed = precompute_htf_series(normalized_df)
    snapshot = build_mtf_snapshot(normalized_df, decision_ts, config, precomputed=precomputed)
    snapshot_dict = snapshot_to_dict(snapshot)
    consensus_bias = derive_htf_consensus_bias(snapshot_dict)
    bias_hint = consensus_bias if consensus_bias in {"bullish", "bearish"} else None
    input_type = "hybrid" if screenshot_meta else "ohlcv"

    analysis, _ = analyze_dataframe(
        df=visible_df,
        symbol=symbol,
        timeframe="15m",
        config=config,
        bias_hint=bias_hint,
        notes=notes,
        input_type=input_type,
    )

    quality = data_quality_report(normalized_df, expected_step_minutes=expected_step_minutes)
    case_id_time = decision_ts.strftime("%Y%m%d_%H%M%S")
    payload = {
        "case_version": CASE_VERSION,
        "case_id": f"{symbol.upper()}_{case_id_time}_{case_kind}",
        "case_kind": case_kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol.upper(),
        "exchange": exchange.upper() if exchange else None,
        "decision_time": decision_ts.isoformat(),
        "data": {
            "source_name": data_source_name,
            "source_csv": str(ohlcv_path.resolve()),
            "source_csv_sha256": file_sha256(ohlcv_path),
            "quality": quality,
            "visible_15m_bars_at_decision": int(len(visible_df)),
            "last_visible_15m_candle": last_visible.isoformat(),
            "decision_minus_last_visible_candle_minutes": round(
                float((decision_ts - last_visible) / pd.Timedelta(minutes=1)),
                4,
            ),
            "no_future_leakage_rule": NO_LEAKAGE_RULE,
            "htf_resample_source": "15m OHLCV resampled in-process to 1H, 4H, 1D",
        },
        "chart_evidence": screenshot_meta,
        "source_alignment": {
            "ohlcv_exchange": exchange.upper() if exchange else None,
            "tradingview_symbol": screenshot_meta.get("tradingview_symbol") if screenshot_meta else None,
            "chart_exchange_matches_ohlcv": _chart_source_matches(exchange, screenshot_meta),
            "needs_human_visual_review": True,
        },
        "mtf_snapshot": snapshot_dict,
        "machine_analysis": analysis.model_dump(mode="json"),
        "expert_label": expert_label_scaffold(),
    }
    return payload


def build_machine_report(payload: dict[str, Any]) -> str:
    analysis = payload["machine_analysis"]
    plan = analysis["trade_plan"]
    mtf = payload["mtf_snapshot"]
    data = payload["data"]
    chart_evidence = payload.get("chart_evidence") or {}
    lines = [
        f"# SMC Case Machine Report - {payload['case_id']}",
        "",
        f"Symbol: {payload['symbol']}",
        f"Exchange: {payload.get('exchange') or 'unspecified'}",
        f"Decision time: {payload['decision_time']}",
        f"Source CSV: {data['source_csv']}",
        f"CSV SHA256: {data['source_csv_sha256']}",
        "",
        "## Verdict",
        f"{plan['verdict']} / Grade {plan['setup_grade']} / Risk {plan['risk_pct']:.1f}%",
        f"Direction: {plan['direction']}",
        f"Confluence: {plan['confluence_score']:.2f}",
        "",
        "## MTF Context",
        f"1H: {mtf['1h']['bias']} ({mtf['1h']['last_structure_label']})",
        f"4H: {mtf['4h']['bias']} ({mtf['4h']['last_structure_label']})",
        f"1D: {mtf['1d']['bias']} ({mtf['1d']['last_structure_label']})",
        f"Alignment: {mtf['alignment']} ({mtf['agreement_ratio']:.2f})",
        "",
        "## Thesis",
        plan["thesis"],
        "",
        "## Key Levels",
        f"Entry zone: {plan.get('entry_low')} - {plan.get('entry_high')}",
        f"Execution SL / invalidation: {plan.get('invalidation')}",
        f"Structural invalidation: {plan.get('structural_invalidation')}",
        f"Stop quality: {plan.get('stop_quality')} ({plan.get('stop_buffer_atr')} ATR)",
        f"Targets: {', '.join(str(target) for target in plan.get('targets', [])) or 'None'}",
        f"Risk/reward: {plan.get('risk_reward')}",
        "",
        "## Checklist",
    ]
    lines.extend(f"- [{'x' if value else ' '}] {key.replace('_', ' ')}" for key, value in plan.get("checklist", {}).items())
    lines.extend(["", "## Warnings"])
    warnings = plan.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- None.")
    if chart_evidence:
        lines.extend(["", "## TradingView Evidence"])
        lines.append(f"TradingView symbol: {chart_evidence.get('tradingview_symbol') or 'unknown'}")
        for tf, path in (chart_evidence.get("screenshots") or {}).items():
            lines.append(f"- {tf}: {path}")
    lines.extend(
        [
            "",
            "## Data Quality",
            f"Rows: {data['quality']['rows']}",
            f"Period: {data['quality']['start']} to {data['quality']['end']}",
            f"Last visible 15m candle: {data['last_visible_15m_candle']} ({data['decision_minus_last_visible_candle_minutes']} minutes before decision)",
            f"Gaps: {data['quality']['gap_count']}",
            f"Duplicate timestamps: {data['quality']['duplicate_timestamps']}",
            f"NaN OHLC rows: {data['quality']['nan_ohlc_rows']}",
            "",
            "Research support only. This is not financial advice or an execution instruction.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_human_label_template(payload: dict[str, Any]) -> str:
    lines = [
        f"# Expert Label Template - {payload['case_id']}",
        "",
        "Use this to turn the machine case into training data. Fill this in after visual chart review.",
        "",
        "## Expert Read",
        "- Expert bias:",
        "- HTF narrative:",
        "- Dealing range:",
        "- Liquidity swept:",
        "- POI quality:",
        "- Confirmation quality:",
        "- Grade (A+ / A / B / C / Pass):",
        "- Verdict (take / wait / pass):",
        "- Entry model:",
        "- Structural invalidation:",
        "- Execution stop:",
        "- Targets:",
        "",
        "## Outcome",
        "- Trade taken:",
        "- Entry:",
        "- Stop:",
        "- Target:",
        "- Result in R:",
        "- What worked:",
        "- What failed:",
        "- Mistake tags:",
        "",
        "## Correction For The Engine",
        "- Should the engine agree with the expert? yes/no",
        "- If no, what rule or label needs correction?",
        "- Does this become a gold-standard training case? yes/no",
        "",
    ]
    return "\n".join(lines)


def build_review_packet_markdown(payload: dict[str, Any]) -> str:
    analysis = payload["machine_analysis"]
    plan = analysis["trade_plan"]
    chart_evidence = payload.get("chart_evidence") or {}
    screenshots = chart_evidence.get("screenshots") or {}
    missing = [key.replace("_", " ") for key, value in plan.get("checklist", {}).items() if value is False]

    lines = [
        f"# SMC Review Packet - {payload['case_id']}",
        "",
        "Use this packet to decide whether the machine read agrees with an expert SMC read.",
        "",
        "## Machine Read",
        f"- Symbol: {payload['symbol']}",
        f"- Exchange: {payload.get('exchange') or 'unspecified'}",
        f"- Decision time: {payload['decision_time']}",
        f"- TradingView symbol: {chart_evidence.get('tradingview_symbol') or 'unknown'}",
        f"- Verdict: {plan['verdict']} / Grade {plan['setup_grade']} / Risk {plan['risk_pct']:.1f}%",
        f"- Direction: {plan['direction']}",
        f"- Confluence: {plan['confluence_score']:.2f}",
        f"- Missing checks: {', '.join(missing) if missing else 'none'}",
        "",
        "## Thesis",
        plan["thesis"],
        "",
        "## Chart Evidence",
    ]
    for timeframe in ["1D", "4H", "1H", "15"]:
        path = screenshots.get(timeframe)
        if not path:
            continue
        lines.extend([f"### {timeframe}", f"![{payload['symbol']} {timeframe}]({path})", ""])

    lines.extend(
        [
            "## Expert Review",
            "- Does the HTF bias match what you see?",
            "- Is the dealing range anchored correctly?",
            "- Is the selected POI actually the best one on the chart?",
            "- Was liquidity genuinely swept, or did the engine over-read it?",
            "- Is the missing confirmation correct?",
            "- Final expert verdict: take / wait / pass",
            "- Should this become a gold-standard training case? yes/no",
            "",
            "Research support only. This is not financial advice or an execution instruction.",
            "",
        ]
    )
    return "\n".join(lines)


def write_case_files(output_dir: Path, payload: dict[str, Any]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "case_json": output_dir / "case.json",
        "machine_report": output_dir / "machine_report.md",
        "human_label": output_dir / "human_label.md",
        "review_packet": output_dir / "review_packet.md",
    }
    paths["case_json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paths["machine_report"].write_text(build_machine_report(payload), encoding="utf-8")
    paths["human_label"].write_text(build_human_label_template(payload), encoding="utf-8")
    paths["review_packet"].write_text(build_review_packet_markdown(payload), encoding="utf-8")
    return paths
